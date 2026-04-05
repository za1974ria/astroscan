# -*- coding: utf-8 -*-
"""
AstroScan — synchronisation de vue (/ws/view-sync).

Variables d'environnement :
  - REDIS_URL
  - VIEW_SYNC_LAST_TTL, VIEW_SYNC_MASTER_TTL, VIEW_SYNC_MASTER_STALE, VIEW_SYNC_HEARTBEAT_TTL
  - VIEW_SYNC_SESSION_KEY — si défini, WS : ?sessionKey= (compare_digest)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

VIEW_SYNC_MAX_BYTES = 65536
LAST_STATE_TTL_SECONDS = int(os.environ.get("VIEW_SYNC_LAST_TTL", "604800"))
MASTER_LOCK_TTL_SECONDS = int(os.environ.get("VIEW_SYNC_MASTER_TTL", "86400"))
# Master considéré mort si pas de heartbeat / activité dans ce délai
MASTER_STALE_SECONDS = float(os.environ.get("VIEW_SYNC_MASTER_STALE", "15"))
HEARTBEAT_REDIS_TTL_SECONDS = int(os.environ.get("VIEW_SYNC_HEARTBEAT_TTL", "18"))

log = logging.getLogger(__name__)


def _channel_for_session(sid: str) -> str:
    h = hashlib.sha256(sid.encode("utf-8")).hexdigest()
    return f"astroscan:view:{h}"


def _last_key_for_session(sid: str) -> str:
    h = hashlib.sha256(sid.encode("utf-8")).hexdigest()
    return f"astroscan:view:last:{h}"


def _master_key_for_session(sid: str) -> str:
    h = hashlib.sha256(sid.encode("utf-8")).hexdigest()
    return f"astroscan:view:master:{h}"


def _heartbeat_key_for_session(sid: str) -> str:
    h = hashlib.sha256(sid.encode("utf-8")).hexdigest()
    return f"astroscan:view:heartbeat:{h}"


def _sanitize_device(raw: str) -> str:
    s = (raw or "").strip()[:256]
    if not s:
        return ""
    out = []
    for c in s:
        o = ord(c)
        if 33 <= o <= 126 and c not in '"\\':
            out.append(c)
    t = "".join(out)
    if len(t) < 1:
        h = hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()[:12]
        return "anon-" + h
    return t[:256]


class _LocalRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, List[Any]] = {}
        self._last_raw: Dict[str, str] = {}

    def add(self, sid: str, ws: Any) -> None:
        with self._lock:
            self._sessions.setdefault(sid, []).append(ws)

    def remove(self, sid: str, ws: Any) -> None:
        with self._lock:
            lst = self._sessions.get(sid)
            if not lst:
                return
            if ws in lst:
                lst.remove(ws)
            if len(lst) == 0:
                del self._sessions[sid]

    def peers(self, sid: str) -> List[Any]:
        with self._lock:
            return list(self._sessions.get(sid, []))

    def broadcast_except(self, sid: str, sender_ws: Any, raw: str) -> None:
        for other in self.peers(sid):
            if other is sender_ws:
                continue
            try:
                other.send(raw)
            except Exception:
                pass

    def broadcast_all(self, sid: str, raw: str) -> None:
        for ws in self.peers(sid):
            try:
                ws.send(raw)
            except Exception:
                pass

    def set_last_local(self, sid: str, raw: str) -> None:
        with self._lock:
            self._last_raw[sid] = raw

    def get_last_local(self, sid: str) -> Optional[str]:
        with self._lock:
            return self._last_raw.get(sid)


class ViewSyncHub:
    def __init__(self) -> None:
        self._local = _LocalRegistry()
        self._master_lock = threading.Lock()
        self._local_master_holder: Dict[str, str] = {}
        self._last_heartbeat_ts: Dict[str, float] = {}
        self._ws_meta: Dict[int, Dict[str, Any]] = {}
        self._meta_lock = threading.Lock()
        self._monitored_sessions: Set[str] = set()
        self._active_master_sessions: Set[str] = set()
        self._redis_client = None
        self._redis_pubsub = None
        self._redis_thread: Optional[threading.Thread] = None
        self._redis_stop = threading.Event()
        self._watchdog_stop = threading.Event()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            name="astroscan-view-sync-watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()

        url = (os.environ.get("REDIS_URL") or "").strip()
        if not url:
            log.info(
                "VIEW_SYNC: Redis indisponible (REDIS_URL absent) — mode local mono-processus."
            )
            return
        try:
            import redis  # type: ignore
        except ImportError:
            log.warning("VIEW_SYNC: paquet 'redis' absent — fallback local.")
            return
        try:
            self._redis_client = redis.Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=2.0,
            )
            self._redis_client.ping()
            self._redis_pubsub = self._redis_client.pubsub(ignore_subscribe_messages=True)
            self._redis_pubsub.psubscribe("astroscan:view:*")
            self._redis_thread = threading.Thread(
                target=self._redis_listen_loop,
                name="astroscan-view-sync-redis",
                daemon=True,
            )
            self._redis_thread.start()
            log.info("VIEW_SYNC: Redis OK — pub/sub + persistance + master + heartbeat.")
            log.info("VIEW_SYNC: OK MULTI-WORKER — Redis actif (diffusion inter-workers).")
        except Exception as e:
            log.warning("VIEW_SYNC: Redis échoué (%s) — fallback local.", e)
            self._redis_client = None
            self._redis_pubsub = None

    def _redis_active(self) -> bool:
        return self._redis_client is not None

    def _redis_listen_loop(self) -> None:
        assert self._redis_pubsub is not None
        while not self._redis_stop.is_set():
            try:
                msg = self._redis_pubsub.get_message(timeout=0.5)
            except Exception:
                continue
            if not msg or msg.get("type") != "pmessage":
                continue
            data = msg.get("data")
            if not isinstance(data, str):
                continue
            if len(data) > VIEW_SYNC_MAX_BYTES:
                continue
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if not isinstance(obj, dict) or obj.get("type") != "VIEW_STATE":
                continue
            sid = obj.get("sessionId")
            if not isinstance(sid, str):
                continue
            log.debug(
                "VIEW_SYNC: broadcast redis → local session=%s bytes=%d",
                sid,
                len(data),
            )
            self._local.broadcast_all(sid, data)

    def shutdown(self) -> None:
        self._watchdog_stop.set()
        self._redis_stop.set()
        if self._redis_pubsub:
            try:
                self._redis_pubsub.close()
            except Exception:
                pass

    def _get_master_holder(self, sid: str) -> Optional[str]:
        if self._redis_client:
            try:
                v = self._redis_client.get(_master_key_for_session(sid))
                return v if isinstance(v, str) and v else None
            except Exception:
                return None
        with self._master_lock:
            return self._local_master_holder.get(sid)

    def _heartbeat_fresh(self, sid: str) -> bool:
        if self._redis_client:
            try:
                return bool(self._redis_client.exists(_heartbeat_key_for_session(sid)))
            except Exception:
                return True
        with self._master_lock:
            ts = self._last_heartbeat_ts.get(sid, 0.0)
        return (time.time() - ts) < MASTER_STALE_SECONDS

    def _touch_heartbeat(self, sid: str, device: str) -> None:
        now = time.time()
        with self._master_lock:
            self._last_heartbeat_ts[sid] = now
        if self._redis_client:
            try:
                self._redis_client.set(
                    _heartbeat_key_for_session(sid),
                    device,
                    ex=HEARTBEAT_REDIS_TTL_SECONDS,
                )
            except Exception:
                pass

    def _downgrade_master_ws_for_session(
        self, sid: str, holder_device: str, reason: str
    ) -> None:
        raw = json.dumps(
            {
                "type": "ROLE_UPDATE",
                "role": "viewer",
                "reason": reason,
                "sessionId": sid,
            },
            separators=(",", ":"),
        )
        for peer in self._local.peers(sid):
            m = self._get_ws_meta(peer)
            if (
                not m
                or m.get("device") != holder_device
                or not m.get("holds_master_lock")
            ):
                continue
            m["holds_master_lock"] = False
            m["can_emit"] = False
            m["effective_role"] = "viewer"
            self._set_ws_meta(peer, m)
            try:
                peer.send(raw)
            except Exception:
                pass

    def _release_master_key_only(self, sid: str, holder: str) -> None:
        if self._redis_client:
            try:
                key = _master_key_for_session(sid)
                cur = self._redis_client.get(key)
                if cur == holder:
                    self._redis_client.delete(key)
            except Exception:
                pass
        else:
            with self._master_lock:
                if self._local_master_holder.get(sid) == holder:
                    del self._local_master_holder[sid]
        self._active_master_sessions.discard(sid)
        with self._master_lock:
            self._last_heartbeat_ts.pop(sid, None)

    def _maybe_timeout_master(self, sid: str) -> None:
        holder = self._get_master_holder(sid)
        if not holder:
            self._active_master_sessions.discard(sid)
            return
        if self._heartbeat_fresh(sid):
            return
        log.info(
            "VIEW_SYNC: MASTER TIMEOUT session=%s holder=%s (heartbeat > %ss)",
            sid,
            holder,
            int(MASTER_STALE_SECONDS),
        )
        self._downgrade_master_ws_for_session(sid, holder, "master_timeout")
        self._release_master_key_only(sid, holder)
        log.info("VIEW_SYNC: MASTER RELEASED session=%s device=%s (timeout)", sid, holder)

    def _watchdog_loop(self) -> None:
        while not self._watchdog_stop.wait(5.0):
            for sid in list(self._monitored_sessions):
                try:
                    self._maybe_timeout_master(sid)
                except Exception:
                    pass

    def _try_claim_master(self, sid: str, device: str) -> Tuple[bool, Optional[str]]:
        if self._redis_client:
            key = _master_key_for_session(sid)
            try:
                ok = bool(
                    self._redis_client.set(
                        key, device, nx=True, ex=MASTER_LOCK_TTL_SECONDS
                    )
                )
                if ok:
                    self._active_master_sessions.add(sid)
                    return True, None
                cur = self._redis_client.get(key)
                if cur == device:
                    self._active_master_sessions.add(sid)
                    return True, None
                return False, cur
            except Exception as e:
                log.warning("VIEW_SYNC: master lock Redis %s — repli mémoire.", e)
        with self._master_lock:
            cur = self._local_master_holder.get(sid)
            if cur is None:
                self._local_master_holder[sid] = device
                self._active_master_sessions.add(sid)
                return True, None
            if cur == device:
                self._active_master_sessions.add(sid)
                return True, None
            return False, cur

    def _release_master(self, sid: str, device: str) -> None:
        if self._redis_client:
            try:
                key = _master_key_for_session(sid)
                cur = self._redis_client.get(key)
                if cur == device:
                    self._redis_client.delete(key)
                    log.info(
                        "VIEW_SYNC: MASTER RELEASED session=%s device=%s (redis)",
                        sid,
                        device,
                    )
            except Exception as e:
                log.warning("VIEW_SYNC: master release Redis %s", e)
        else:
            with self._master_lock:
                if self._local_master_holder.get(sid) == device:
                    del self._local_master_holder[sid]
                    log.info(
                        "VIEW_SYNC: MASTER RELEASED session=%s device=%s (local)",
                        sid,
                        device,
                    )
        self._active_master_sessions.discard(sid)
        with self._master_lock:
            self._last_heartbeat_ts.pop(sid, None)

    def _persist_last(self, sid: str, raw: str) -> None:
        self._local.set_last_local(sid, raw)
        if self._redis_client:
            try:
                self._redis_client.set(
                    _last_key_for_session(sid),
                    raw,
                    ex=LAST_STATE_TTL_SECONDS,
                )
            except Exception:
                pass

    def _load_last_raw(self, sid: str) -> Optional[str]:
        if self._redis_client:
            try:
                v = self._redis_client.get(_last_key_for_session(sid))
                if isinstance(v, str) and v:
                    self._local.set_last_local(sid, v)
                    return v
            except Exception:
                pass
        return self._local.get_last_local(sid)

    @staticmethod
    def _envelope_for_init(stored_raw: str) -> Optional[str]:
        try:
            obj = json.loads(stored_raw)
        except Exception:
            return None
        if not isinstance(obj, dict):
            return None
        obj["messageKind"] = "init"
        try:
            return json.dumps(obj, separators=(",", ":"))
        except Exception:
            return None

    def _set_ws_meta(self, ws: Any, meta: Dict[str, Any]) -> None:
        with self._meta_lock:
            self._ws_meta[id(ws)] = meta

    def _pop_ws_meta(self, ws: Any) -> Optional[Dict[str, Any]]:
        with self._meta_lock:
            return self._ws_meta.pop(id(ws), None)

    def _get_ws_meta(self, ws: Any) -> Optional[Dict[str, Any]]:
        with self._meta_lock:
            return self._ws_meta.get(id(ws))

    def _send_json(self, ws: Any, payload: Dict[str, Any]) -> None:
        try:
            ws.send(json.dumps(payload, separators=(",", ":")))
        except Exception:
            pass

    def _promote_ws_to_master(self, ws: Any, sid: str, device: str) -> None:
        meta = self._get_ws_meta(ws)
        if not meta:
            return
        meta["holds_master_lock"] = True
        meta["can_emit"] = True
        meta["effective_role"] = "master"
        self._set_ws_meta(ws, meta)
        self._touch_heartbeat(sid, device)
        self._send_json(
            ws,
            {
                "type": "ROLE_UPDATE",
                "role": "master",
                "reason": "accepted",
                "sessionId": sid,
            },
        )
        log.info("VIEW_SYNC: MASTER TAKEOVER / PROMOTE session=%s device=%s", sid, device)

    def client_connected(
        self, ws: Any, sid: str, view_role: str, source_device: str
    ) -> None:
        self._monitored_sessions.add(sid)
        self._local.add(sid, ws)
        role = (view_role or "master").strip().lower()
        if role not in ("master", "viewer", "collaborative"):
            role = "master"
        device = _sanitize_device(source_device)
        if not device:
            device = "anon-" + hashlib.sha256(str(id(ws)).encode()).hexdigest()[:10]

        wants_master_slot = role in ("master", "collaborative")
        effective_role = role
        holds_lock = False
        can_emit = False

        if wants_master_slot:
            ok, other = self._try_claim_master(sid, device)
            if ok:
                holds_lock = True
                can_emit = True
                self._touch_heartbeat(sid, device)
                log.info(
                    "VIEW_SYNC: MASTER ACCEPTED session=%s device=%s role=%s redis=%s",
                    sid,
                    device,
                    role,
                    self._redis_active(),
                )
            else:
                effective_role = "viewer"
                can_emit = False
                self._send_json(
                    ws,
                    {
                        "type": "ROLE_UPDATE",
                        "role": "viewer",
                        "reason": "master_already_exists",
                        "sessionId": sid,
                        "holderDevice": other,
                    },
                )
                log.info(
                    "VIEW_SYNC: MASTER DOWNGRADED session=%s device=%s (holder=%s)",
                    sid,
                    device,
                    other,
                )
        else:
            log.info(
                "VIEW_SYNC: connect session=%s device=%s viewer redis=%s",
                sid,
                device,
                self._redis_active(),
            )

        self._set_ws_meta(
            ws,
            {
                "sid": sid,
                "device": device,
                "requested_role": role,
                "effective_role": effective_role,
                "holds_master_lock": holds_lock,
                "can_emit": can_emit,
            },
        )

        last = self._load_last_raw(sid)
        if last:
            init_raw = self._envelope_for_init(last)
            if init_raw and len(init_raw) <= VIEW_SYNC_MAX_BYTES:
                try:
                    ws.send(init_raw)
                    log.info(
                        "VIEW_SYNC: init state envoyé session=%s bytes=%d",
                        sid,
                        len(init_raw),
                    )
                except Exception:
                    pass

    def client_disconnected(self, ws: Any, sid: str) -> None:
        meta = self._pop_ws_meta(ws)
        if meta and meta.get("holds_master_lock"):
            self._release_master(sid, meta["device"])
        self._local.remove(sid, ws)

    def on_heartbeat(self, ws: Any, sid: str, obj: Dict[str, Any]) -> None:
        meta = self._get_ws_meta(ws)
        if not meta or not meta.get("holds_master_lock"):
            return
        self._touch_heartbeat(sid, meta["device"])
        log.debug("VIEW_SYNC: HEARTBEAT session=%s device=%s", sid, meta["device"])

    def on_request_master(self, ws: Any, sid: str, obj: Dict[str, Any]) -> None:
        meta = self._get_ws_meta(ws)
        if not meta:
            return
        device = meta["device"]
        holder = self._get_master_holder(sid)

        if meta.get("holds_master_lock") and holder == device:
            self._send_json(
                ws,
                {
                    "type": "ROLE_UPDATE",
                    "role": "master",
                    "reason": "already_master",
                    "sessionId": sid,
                },
            )
            return

        if holder is None:
            ok, _ = self._try_claim_master(sid, device)
            if ok:
                self._promote_ws_to_master(ws, sid, device)
            return

        if holder == device:
            ok, _ = self._try_claim_master(sid, device)
            if ok:
                self._promote_ws_to_master(ws, sid, device)
            return

        if self._heartbeat_fresh(sid):
            self._send_json(
                ws,
                {
                    "type": "ROLE_UPDATE",
                    "role": "viewer",
                    "reason": "master_active",
                    "sessionId": sid,
                },
            )
            log.info("VIEW_SYNC: REQUEST_MASTER refusé session=%s (master actif)", sid)
            return

        self._downgrade_master_ws_for_session(sid, holder, "taken_over")
        self._release_master_key_only(sid, holder)
        ok, _ = self._try_claim_master(sid, device)
        if ok:
            self._promote_ws_to_master(ws, sid, device)
        else:
            self._send_json(
                ws,
                {
                    "type": "ROLE_UPDATE",
                    "role": "viewer",
                    "reason": "takeover_failed",
                    "sessionId": sid,
                },
            )

    def on_client_message(self, ws: Any, sid: str, raw: str, obj: Dict[str, Any]) -> None:
        meta = self._get_ws_meta(ws)
        if not meta or not meta.get("can_emit"):
            log.debug(
                "VIEW_SYNC: VIEW_STATE ignoré session=%s device=%s",
                sid,
                (meta or {}).get("device"),
            )
            return

        if meta.get("holds_master_lock"):
            self._touch_heartbeat(sid, meta["device"])

        to_store = {k: v for k, v in obj.items() if k != "messageKind"}
        try:
            stable = json.dumps(to_store, separators=(",", ":"), default=str)
        except Exception:
            stable = raw
        if len(stable) > VIEW_SYNC_MAX_BYTES:
            return

        self._persist_last(sid, stable)

        if self._redis_client and meta.get("holds_master_lock"):
            try:
                self._redis_client.expire(
                    _master_key_for_session(sid), MASTER_LOCK_TTL_SECONDS
                )
            except Exception:
                pass

        if self._redis_client:
            try:
                self._redis_client.publish(_channel_for_session(sid), stable)
                log.debug("VIEW_SYNC: publish redis session=%s", sid)
            except Exception:
                pass
            return

        log.debug("VIEW_SYNC: broadcast local session=%s", sid)
        self._local.broadcast_except(sid, ws, stable)


_hub: Optional[ViewSyncHub] = None
_hub_lock = threading.Lock()


def get_view_sync_hub() -> ViewSyncHub:
    global _hub
    with _hub_lock:
        if _hub is None:
            _hub = ViewSyncHub()
        return _hub


def get_expected_session_key() -> str:
    return (os.environ.get("VIEW_SYNC_SESSION_KEY") or "").strip()
