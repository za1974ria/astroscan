"""SCAN A SIGNAL — AISStream subscriber (multi-worker safe).

Background daemon thread that maintains a WebSocket connection to
wss://stream.aisstream.io/v0/stream and writes:

  • PositionReport   → as:scan:vessels (latest kinematic state per MMSI)
  • PositionReport   → as:scan:vessels_history:<mmsi> (rolling 50-pt track)
  • PositionReport   → as:scan:vessels_first_seen   (when ASTRO-SCAN first
                                                     locked onto this MMSI)
  • ShipStaticData   → as:scan:vessels_static       (Type 5 — destination,
                                                     ETA, dimensions, etc.)

Multi-worker safety (Gunicorn 4-worker setup):
  Only ONE worker may hold an active WebSocket subscription at a time —
  AISStream rate-limits a single API key with 429s when multiple parallel
  connections share it. Election is done via a Redis distributed lock
  (SET NX EX, refreshed by a heartbeat thread). Other workers stay in
  standby and only read from the cache populated by the elected worker.

  - LOCK_KEY    : astroscan:lock:aisstream_subscriber
  - LOCK_TTL    : 90 s (heartbeat refresh every 30 s)
  - On lock loss the elected worker closes its WebSocket and re-enters
    the standby loop. A dead worker stops refreshing → another worker
    elects itself within ~LOCK_TTL.

Designed to fail-soft: if the websocket-client package, the
AISSTREAM_API_KEY env var, or Redis is missing, the subscriber stays
inert and the vessel API endpoints return empty results.

Reference: https://aisstream.io/documentation
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone

try:
    import websocket  # websocket-client package
except Exception:  # pragma: no cover
    websocket = None

log = logging.getLogger(__name__)

_AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"

# ──────────────────────────────────────────────────────────────────────
# Distributed lock (Redis SET NX EX)
# ──────────────────────────────────────────────────────────────────────

# Per-process unique ID. Two workers in the same process couldn't both
# hold the lock anyway (they'd share globals), so PID + short UUID is
# sufficient and lets us spot which worker is elected from the logs.
WORKER_ID = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"

LOCK_KEY = "astroscan:lock:aisstream_subscriber"
LOCK_TTL = 90              # seconds — survives a Gunicorn graceful timeout
HEARTBEAT_INTERVAL = 30    # refresh cadence (LOCK_TTL / 3 — comfortable margin)
STANDBY_RETRY_INTERVAL = 60  # how long a non-elected worker sleeps between probes

# Backoff escalation on connection errors while still holding the lock.
BACKOFF_INITIAL = 60
BACKOFF_MAX = 480          # 8 min cap
STABLE_RESET_SEC = 300     # 5 min of stable connection clears the backoff

# Atomic refresh: only refresh if we still own the key. Prevents a stale
# worker from stealing the lock back after losing it.
_LUA_REFRESH = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
else
    return 0
end
"""

# Atomic release: only DEL if we own the key.
_LUA_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def try_acquire_lock(redis_client) -> bool:
    """Attempt to become the AISStream subscriber. True if elected."""
    if redis_client is None:
        return False
    try:
        return bool(redis_client.set(LOCK_KEY, WORKER_ID, nx=True, ex=LOCK_TTL))
    except Exception as exc:
        log.warning("[scan_signal] AISStream lock acquire failed: %s", exc)
        return False


def refresh_lock(redis_client) -> bool:
    """Refresh the lock TTL if we still own it. Atomic via Lua."""
    if redis_client is None:
        return False
    try:
        return redis_client.eval(_LUA_REFRESH, 1, LOCK_KEY, WORKER_ID, LOCK_TTL) == 1
    except Exception as exc:
        log.warning("[scan_signal] AISStream lock refresh failed: %s", exc)
        return False


def release_lock(redis_client) -> None:
    """Release the lock if we own it. No-op otherwise (atomic via Lua)."""
    if redis_client is None:
        return
    try:
        redis_client.eval(_LUA_RELEASE, 1, LOCK_KEY, WORKER_ID)
    except Exception:
        pass


def _read_lock_holder(redis_client) -> str | None:
    if redis_client is None:
        return None
    try:
        v = redis_client.get(LOCK_KEY)
        if v is None:
            return None
        return v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
    except Exception:
        return None

# Live state (latest position per MMSI)
_REDIS_KEY_VESSELS = "as:scan:vessels"
_REDIS_KEY_BY_NAME = "as:scan:vessels_by_name"
_REDIS_TTL_SECONDS = 7200  # 2h

# Static (Type 5) data — destination, ETA, dimensions
_REDIS_KEY_STATIC = "as:scan:vessels_static"
_REDIS_TTL_STATIC = 86400  # 24h (Type 5 is broadcast every ~6 min)

# Position history — used for "provenance" reverse-geocoding
_REDIS_KEY_HISTORY_PREFIX = "as:scan:vessels_history:"
_REDIS_TTL_HISTORY = 7 * 24 * 3600  # 7 days
_HISTORY_MAX = 50
# Down-sample history writes: don't push every position (~1 msg/s) — keep
# at most one entry every _HISTORY_MIN_INTERVAL seconds per MMSI.
_HISTORY_MIN_INTERVAL = 600  # 10 min

# First-seen — used for "tracked since" duration
_REDIS_KEY_FIRST_SEEN = "as:scan:vessels_first_seen"
_REDIS_TTL_FIRST_SEEN = 7 * 24 * 3600  # 7 days


class AISStreamSubscriber:
    """Maintains a WebSocket subscription to AISStream and writes vessels to Redis."""

    def __init__(self, redis_client, max_vessels: int = 500):
        self.api_key = os.getenv("AISSTREAM_API_KEY", "").strip()
        self.redis = redis_client
        self.max_vessels = int(max_vessels)
        self.ws = None
        self.thread: threading.Thread | None = None
        self.running = False
        self.connected = False
        self.last_message_at: datetime | None = None
        self.message_count = 0
        self.static_count = 0
        self.error_count = 0
        self.last_error: str | None = None
        # in-memory throttle for history writes: mmsi -> last write epoch
        self._history_last: dict[str, float] = {}

        # Multi-worker lock state
        self.is_elected: bool = False
        self._lock_lost_event: threading.Event = threading.Event()
        self._heartbeat_stop: threading.Event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not self.api_key:
            log.warning("[scan_signal] AISSTREAM_API_KEY missing — vessel tracker disabled")
            return
        if websocket is None:
            log.error("[scan_signal] websocket-client package not installed — vessel tracker disabled")
            return
        if self.running:
            log.info("[scan_signal] AISStream subscriber already running")
            return
        if self.redis is None:
            log.error("[scan_signal] Redis unavailable — vessel tracker disabled")
            return
        self.running = True
        self.thread = threading.Thread(
            target=self._run, name="aisstream-subscriber", daemon=True,
        )
        self.thread.start()
        log.info("[scan_signal] AISStream subscriber thread started")

    def stop(self) -> None:
        self.running = False
        self._stop_event.set()
        self._heartbeat_stop.set()
        try:
            if self.ws is not None:
                self.ws.close()
        except Exception:
            pass
        # Voluntarily release the lock so another worker can take over
        # immediately rather than waiting for TTL expiry.
        if self.is_elected:
            release_lock(self.redis)
            self.is_elected = False

    # ------------------------------------------------------------------
    # WebSocket loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main daemon loop.

        Phase 1 — election: try to acquire the Redis lock. If another
        worker holds it, sleep STANDBY_RETRY_INTERVAL and retry. We never
        give up: if the elected worker dies, its lock TTL expires and we
        take over.

        Phase 2 — connection: holding the lock, start the heartbeat
        thread and run the WebSocket. On clean disconnects we re-enter
        with backoff. On lock loss we abandon the connection and go
        back to phase 1 (without applying error backoff).
        """
        err_count = 0
        last_standby_log = 0.0
        while self.running:
            # ---------- Phase 1: election ----------
            if not try_acquire_lock(self.redis):
                holder = _read_lock_holder(self.redis)
                # Throttle the standby log to once every 5 minutes per worker
                # (we probe every 60s but don't need to spam the journal).
                now_ts = time.time()
                if now_ts - last_standby_log > 300:
                    log.info(
                        "[scan_signal] AISStream lock held by worker %s, "
                        "standby (worker_id=%s)",
                        holder or "?", WORKER_ID,
                    )
                    last_standby_log = now_ts
                self._sleep_interruptible(STANDBY_RETRY_INTERVAL)
                continue

            # We won the election.
            self.is_elected = True
            self._lock_lost_event.clear()
            self._heartbeat_stop.clear()
            log.info(
                "[scan_signal] AISStream lock acquired by worker %s",
                WORKER_ID,
            )

            # Start heartbeat (refresh lock every HEARTBEAT_INTERVAL s).
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                name="aisstream-heartbeat",
                daemon=True,
            )
            self._heartbeat_thread.start()

            # ---------- Phase 2: connect & listen ----------
            try:
                connect_start = time.time()
                try:
                    self._connect_and_listen()  # blocks until close/error
                except Exception as exc:
                    self.error_count += 1
                    self.last_error = str(exc)
                    log.warning(
                        "[scan_signal] AISStream loop error: %s", exc
                    )

                if not self.running:
                    break

                if self._lock_lost_event.is_set():
                    # Heartbeat detected we no longer own the lock — back
                    # to standby. Don't apply backoff (it's not our fault).
                    log.warning(
                        "[scan_signal] AISStream lock lost, reconnecting"
                        " (worker %s returns to standby)", WORKER_ID,
                    )
                    err_count = 0
                else:
                    # Connection ended but we still hold the lock — apply
                    # exponential backoff on consecutive errors. Reset
                    # backoff if the connection was stable for >5 min.
                    connect_duration = time.time() - connect_start
                    if connect_duration > STABLE_RESET_SEC:
                        if err_count > 0:
                            log.info(
                                "[scan_signal] AISStream connection was stable "
                                "%ds — backoff counter reset",
                                int(connect_duration),
                            )
                        err_count = 0
                    err_count += 1
                    wait = min(
                        BACKOFF_INITIAL * (2 ** (err_count - 1)),
                        BACKOFF_MAX,
                    )
                    log.warning(
                        "[scan_signal] AISStream backoff escalated to %ds "
                        "after error #%d",
                        wait, err_count,
                    )
                    self._sleep_interruptible(wait)
            finally:
                # Tear down heartbeat regardless of outcome.
                self._heartbeat_stop.set()
                if self._heartbeat_thread is not None:
                    try:
                        self._heartbeat_thread.join(timeout=2)
                    except Exception:
                        pass
                    self._heartbeat_thread = None
                self.is_elected = False

        # On shutdown: best-effort lock release so a sibling worker can
        # take over without waiting for TTL expiry.
        release_lock(self.redis)

    def _heartbeat_loop(self) -> None:
        """Refresh the Redis lock periodically.

        If a refresh fails (TTL expired, lock taken by another worker, or
        Redis blip), we set _lock_lost_event and close the WebSocket so
        _run() exits its connection loop.
        """
        while not self._heartbeat_stop.is_set() and self.running:
            if not refresh_lock(self.redis):
                log.warning(
                    "[scan_signal] AISStream lock refresh failed — "
                    "yielding (worker %s)", WORKER_ID,
                )
                self._lock_lost_event.set()
                try:
                    if self.ws is not None:
                        self.ws.close()
                except Exception:
                    pass
                return
            # Wait until the next tick (interruptible by stop event).
            self._heartbeat_stop.wait(HEARTBEAT_INTERVAL)

    def _sleep_interruptible(self, seconds: float) -> None:
        """Sleep but wake up promptly on stop()."""
        self._stop_event.wait(timeout=max(0.0, float(seconds)))

    def _connect_and_listen(self) -> None:
        self.ws = websocket.WebSocketApp(
            _AISSTREAM_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws.run_forever(ping_interval=30, ping_timeout=10)

    # ------------------------------------------------------------------
    # WebSocket callbacks
    # ------------------------------------------------------------------

    def _on_open(self, ws) -> None:
        self.connected = True
        subscribe = {
            "APIKey": self.api_key,
            "BoundingBoxes": [[[-90.0, -180.0], [90.0, 180.0]]],
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
        }
        try:
            ws.send(json.dumps(subscribe))
            log.info(
                "[scan_signal] AISStream connected, subscribed to "
                "PositionReport + ShipStaticData (global)"
            )
        except Exception as exc:
            log.warning("[scan_signal] AISStream subscribe failed: %s", exc)

    def _on_message(self, ws, message) -> None:
        try:
            data = json.loads(message)
        except Exception:
            return

        msg_type = data.get("MessageType")
        if msg_type == "PositionReport":
            self._handle_position(data)
        elif msg_type == "ShipStaticData":
            self._handle_static(data)

    # ------------------------------------------------------------------
    # PositionReport handling
    # ------------------------------------------------------------------

    def _handle_position(self, data: dict) -> None:
        meta = data.get("MetaData") or {}
        report = (data.get("Message") or {}).get("PositionReport") or {}

        mmsi = meta.get("MMSI") or report.get("UserID")
        if not mmsi:
            return

        try:
            mmsi_str = str(int(mmsi))
        except (TypeError, ValueError):
            return

        lat = meta.get("latitude")
        lon = meta.get("longitude")
        if lat is None:
            lat = report.get("Latitude")
        if lon is None:
            lon = report.get("Longitude")
        if lat is None or lon is None:
            return

        try:
            flat = float(lat)
            flon = float(lon)
        except (TypeError, ValueError):
            return

        name = (meta.get("ShipName") or "").strip() or None
        now = datetime.now(timezone.utc)
        ts_iso = meta.get("time_utc") or now.isoformat()

        vessel = {
            "mmsi": mmsi_str,
            "name": name,
            "latitude": flat,
            "longitude": flon,
            "sog_knots": report.get("Sog"),
            "cog_deg": report.get("Cog"),
            "true_heading_deg": report.get("TrueHeading"),
            "nav_status": report.get("NavigationalStatus"),
            "timestamp": ts_iso,
        }

        try:
            self.redis.hset(_REDIS_KEY_VESSELS, mmsi_str, json.dumps(vessel))
            if name:
                self.redis.hset(_REDIS_KEY_BY_NAME, name.upper(), mmsi_str)
            self.redis.expire(_REDIS_KEY_VESSELS, _REDIS_TTL_SECONDS)
            self.redis.expire(_REDIS_KEY_BY_NAME, _REDIS_TTL_SECONDS)
        except Exception as exc:
            log.debug("[scan_signal] Redis write failed: %s", exc)
            return

        # First-seen tracking — only set if not already present
        try:
            self.redis.hsetnx(_REDIS_KEY_FIRST_SEEN, mmsi_str, now.isoformat())
            self.redis.expire(_REDIS_KEY_FIRST_SEEN, _REDIS_TTL_FIRST_SEEN)
        except Exception as exc:
            log.debug("[scan_signal] first-seen write failed: %s", exc)

        # Position history (down-sampled)
        self._maybe_push_history(mmsi_str, flat, flon, now)

        self.last_message_at = now
        self.message_count += 1

        if self.message_count % 200 == 0:
            self._trim_cache()

    def _maybe_push_history(
        self, mmsi: str, lat: float, lon: float, now: datetime
    ) -> None:
        last = self._history_last.get(mmsi, 0.0)
        epoch = now.timestamp()
        if epoch - last < _HISTORY_MIN_INTERVAL:
            return
        self._history_last[mmsi] = epoch
        key = _REDIS_KEY_HISTORY_PREFIX + mmsi
        entry = json.dumps({"lat": lat, "lon": lon, "ts": now.isoformat()})
        try:
            # LPUSH so index 0 is freshest, -1 is oldest
            self.redis.lpush(key, entry)
            self.redis.ltrim(key, 0, _HISTORY_MAX - 1)
            self.redis.expire(key, _REDIS_TTL_HISTORY)
        except Exception as exc:
            log.debug("[scan_signal] history push failed: %s", exc)

    # ------------------------------------------------------------------
    # ShipStaticData (Type 5) handling
    # ------------------------------------------------------------------

    def _handle_static(self, data: dict) -> None:
        meta = data.get("MetaData") or {}
        static_msg = (data.get("Message") or {}).get("ShipStaticData") or {}

        mmsi = meta.get("MMSI") or static_msg.get("UserID")
        if not mmsi:
            return
        try:
            mmsi_str = str(int(mmsi))
        except (TypeError, ValueError):
            return

        now = datetime.now(timezone.utc)
        dimension = static_msg.get("Dimension") or {}
        try:
            length = int(dimension.get("A", 0) or 0) + int(dimension.get("B", 0) or 0)
            breadth = int(dimension.get("C", 0) or 0) + int(dimension.get("D", 0) or 0)
        except (TypeError, ValueError):
            length = 0
            breadth = 0

        name = (static_msg.get("Name") or meta.get("ShipName") or "").strip()
        callsign = (static_msg.get("CallSign") or "").strip()
        destination = (static_msg.get("Destination") or "").strip()

        static_record = {
            "mmsi": mmsi_str,
            "name": name or None,
            "callsign": callsign or None,
            "destination": destination or None,
            "eta": static_msg.get("Eta"),
            "ship_type": static_msg.get("Type"),
            "imo": static_msg.get("ImoNumber"),
            "length": length or None,
            "breadth": breadth or None,
            "max_static_draught": static_msg.get("MaximumStaticDraught"),
            "updated_at": now.isoformat(),
        }

        try:
            self.redis.hset(_REDIS_KEY_STATIC, mmsi_str, json.dumps(static_record))
            self.redis.expire(_REDIS_KEY_STATIC, _REDIS_TTL_STATIC)
            if name:
                self.redis.hset(_REDIS_KEY_BY_NAME, name.upper(), mmsi_str)
                self.redis.expire(_REDIS_KEY_BY_NAME, _REDIS_TTL_SECONDS)
        except Exception as exc:
            log.debug("[scan_signal] static write failed: %s", exc)
            return

        self.static_count += 1

    # ------------------------------------------------------------------
    # Cache hygiene
    # ------------------------------------------------------------------

    def _trim_cache(self) -> None:
        try:
            keys = self.redis.hkeys(_REDIS_KEY_VESSELS)
            if len(keys) > self.max_vessels:
                drop_n = len(keys) - self.max_vessels
                to_drop = keys[:drop_n]
                if to_drop:
                    self.redis.hdel(_REDIS_KEY_VESSELS, *to_drop)
        except Exception as exc:
            log.debug("[scan_signal] vessel cache trim failed: %s", exc)

    def _on_error(self, ws, error) -> None:
        self.connected = False
        self.error_count += 1
        self.last_error = str(error)
        log.warning("[scan_signal] AISStream error: %s", error)

    def _on_close(self, ws, status, reason) -> None:
        self.connected = False
        log.info("[scan_signal] AISStream closed: %s %s", status, reason)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def get_health(self) -> dict:
        return {
            "configured": bool(self.api_key),
            "websocket_lib": websocket is not None,
            "connected": self.connected,
            "running": self.running,
            "messages_received": self.message_count,
            "static_received": self.static_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            # Multi-worker lock state
            "worker_id": WORKER_ID,
            "is_elected": self.is_elected,
            "lock_holder": _read_lock_holder(self.redis),
            "lock_key": LOCK_KEY,
            "lock_ttl": LOCK_TTL,
        }
