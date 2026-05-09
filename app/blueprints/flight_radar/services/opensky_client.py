"""OpenSky Network OAuth2 client.

Authenticated mode (4000 calls/day) when OPENSKY_CLIENT_ID/SECRET are set,
otherwise falls back to anonymous mode (~100 calls/day, used until quota).
The token is cached in-memory and refreshed 60 s before expiration.

When ScrapingBee is configured (SCRAPINGBEE_API_KEY or SCRAPINGBEE_KEY),
requests can be routed through app.scrapingbee.com for IP rotation after
five consecutive HTTP 429 responses from OpenSky, or immediately when
OPENSKY_USE_SCRAPINGBEE=1.

Third fallback: api.adsb.lol (no key) when OpenSky and ScrapingBee fail or
when OPENSKY_USE_ADSBLOL=1 forces that feed.
"""
from __future__ import annotations

import base64
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import quote_plus, urlencode

import requests

log = logging.getLogger(__name__)

TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/"
    "protocol/openid-connect/token"
)
STATES_URL = "https://opensky-network.org/api/states/all"
SCRAPINGBEE_API = "https://app.scrapingbee.com/api/v1/"

USER_AGENT = "AstroScan/2.0 (+https://astroscan.space)"
CONSEC_429_SB_THRESHOLD = 5

FT_TO_M = 0.3048
KTS_TO_MS = 0.5144
FPM_TO_MS = 0.00508  # ft/min → m/s

# (lat, lon, dist_nm, zone_label) — 10 zones, 250 NM max each
ADSB_LOL_ZONES: tuple[tuple[float, float, int, str], ...] = (
    (50.0, 5.0, 250, "Europe Ouest"),
    (52.0, 30.0, 250, "Europe Est"),
    (52.0, -5.0, 250, "UK/Irlande"),
    (40.0, 15.0, 250, "Méditerranée"),
    (40.0, -75.0, 250, "USA Est"),
    (37.0, -120.0, 250, "USA Ouest"),
    (40.0, -95.0, 250, "USA Centre"),
    (35.0, 130.0, 250, "Asie Est"),
    (10.0, 105.0, 250, "Asie Sud-Est"),
    (-30.0, 140.0, 250, "Australie"),
)


def _truthy_env(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _scrapingbee_response_quota_exhausted(resp: requests.Response) -> bool:
    if resp.status_code != 401:
        return False
    t = (resp.text or "")[:1200].lower()
    if "monthly api calls limit reached" in t:
        return True
    if "monthly" in t and "limit" in t and ("call" in t or "credit" in t):
        return True
    if "quota" in t and ("exceed" in t or "reached" in t):
        return True
    return False


def _adsblol_zone_url(lat: float, lon: float, dist_nm: int) -> str:
    return f"https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist_nm}"


def _ac_to_opensky_state(ac: dict[str, Any], base_now: int) -> list[Any] | None:
    """Convert one adsb.lol aircraft object to an OpenSky state vector (list)."""
    hex_raw = ac.get("hex") or ""
    icao24 = hex_raw.lower().strip()
    if not icao24:
        return None
    lat = ac.get("lat")
    lon = ac.get("lon")
    if lat is None or lon is None:
        return None
    try:
        latf = float(lat)
        lonf = float(lon)
    except (TypeError, ValueError):
        return None

    callsign = (ac.get("flight") or "").strip()

    alt_baro = ac.get("alt_baro")
    on_ground = False
    baro_m: float | None = None
    if isinstance(alt_baro, str) and alt_baro.strip().lower() == "ground":
        on_ground = True
        baro_m = 0.0
    elif alt_baro is not None:
        try:
            baro_m = float(alt_baro) * FT_TO_M
        except (TypeError, ValueError):
            baro_m = None

    geo_m: float | None = None
    alt_geom = ac.get("alt_geom")
    if alt_geom is not None:
        try:
            geo_m = float(alt_geom) * FT_TO_M
        except (TypeError, ValueError):
            geo_m = None

    vel_ms: float | None = None
    gs = ac.get("gs")
    if gs is not None:
        try:
            vel_ms = float(gs) * KTS_TO_MS
        except (TypeError, ValueError):
            vel_ms = None

    true_track: float | None = None
    tr = ac.get("track")
    if tr is not None:
        try:
            true_track = float(tr)
        except (TypeError, ValueError):
            true_track = None

    vr_ms: float | None = None
    br = ac.get("baro_rate")
    if br is not None:
        try:
            vr_ms = float(br) * FPM_TO_MS
        except (TypeError, ValueError):
            vr_ms = None

    seen_pos = ac.get("seen_pos")
    seen = ac.get("seen")
    tp: int | None = None
    if isinstance(seen_pos, (int, float)) and float(seen_pos) > 1e8:
        tp = int(seen_pos)
    elif isinstance(seen_pos, str):
        try:
            v = float(seen_pos)
            if v > 1e8:
                tp = int(v)
        except ValueError:
            tp = None
    lc: int | None = None
    if isinstance(seen, (int, float)) and float(seen) > 1e8:
        lc = int(seen)
    elif isinstance(seen, str):
        try:
            v = float(seen)
            if v > 1e8:
                lc = int(v)
        except ValueError:
            lc = None
    if tp is None:
        tp = base_now
    if lc is None:
        lc = base_now

    squawk_raw = ac.get("squawk")
    squawk: str | None = None
    if squawk_raw is not None and str(squawk_raw).strip():
        squawk = str(squawk_raw).strip()

    return [
        icao24,
        callsign,
        "",
        tp,
        lc,
        lonf,
        latf,
        baro_m,
        on_ground,
        vel_ms,
        true_track,
        vr_ms,
        None,
        geo_m,
        squawk,
        False,
        0,
    ]


def _fetch_adsblol_zone(
    lat: float, lon: float, dist_nm: int, zone_name: str
) -> tuple[str, list[dict[str, Any]], int]:
    """HTTP GET one adsb.lol zone. Returns (zone_name, ac_list, now_ts)."""
    url = _adsblol_zone_url(lat, lon, dist_nm)
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"http {r.status_code}")
    try:
        payload = r.json()
    except ValueError as exc:
        raise RuntimeError(f"invalid json: {exc}") from exc
    ac = payload.get("ac") or []
    if not isinstance(ac, list):
        ac = []
    now_raw = payload.get("now")
    try:
        now_ts = int(now_raw) if now_raw is not None else int(time.time())
    except (TypeError, ValueError):
        now_ts = int(time.time())
    return zone_name, ac, now_ts


class OpenSkyClient:
    """OAuth2 client for the OpenSky Network REST API."""

    def __init__(self) -> None:
        self._client_id = (os.environ.get("OPENSKY_CLIENT_ID") or "").strip()
        self._client_secret = (os.environ.get("OPENSKY_CLIENT_SECRET") or "").strip()
        # Legacy basic-auth fallback (the older OpenSky username/password).
        self._legacy_user = (os.environ.get("OPENSKY_USER") or "").strip()
        self._legacy_pass = (os.environ.get("OPENSKY_PASS") or "").strip()

        self._token: str | None = None
        self._token_exp: float = 0.0
        self._token_lock = threading.Lock()

        self._consecutive_429_direct = 0
        self._auto_sb_enabled = False
        self._force_sb_mode_logged = False
        self._missing_sb_key_logged = False
        self._scrapingbee_last_quota_hit = False

        # Metrics surfaced by /api/flight-radar/health (and introspection)
        self.metrics: dict[str, Any] = {
            "calls": 0,
            "errors": 0,
            "rate_limited": 0,
            "last_success_ts": None,
            "last_error": None,
            "auth_mode": self._auth_mode(),
            "token_expires_in": None,
            "scrapingbee_key_present": False,
            "scrapingbee_used": False,
            "scrapingbee_calls": 0,
            "scrapingbee_errors": 0,
            "adsblol_used": False,
            "adsblol_calls": 0,
            "adsblol_errors": 0,
            "current_source": None,
        }

    @staticmethod
    def _scrapingbee_key() -> str:
        return (
            os.environ.get("SCRAPINGBEE_API_KEY")
            or os.environ.get("SCRAPINGBEE_KEY")
            or ""
        ).strip()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _auth_mode(self) -> str:
        if self._client_id and self._client_secret:
            return "oauth2"
        if self._legacy_user and self._legacy_pass:
            return "basic"
        return "anonymous"

    def has_oauth(self) -> bool:
        return bool(self._client_id and self._client_secret)

    def get_token(self) -> str | None:
        """Return a valid access token (refreshing 60 s before expiry)."""
        if not self.has_oauth():
            return None
        with self._token_lock:
            now = time.time()
            if self._token and now < (self._token_exp - 60):
                self.metrics["token_expires_in"] = int(self._token_exp - now)
                return self._token
            try:
                r = requests.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    },
                    headers={"User-Agent": USER_AGENT},
                    timeout=10,
                )
                r.raise_for_status()
                payload = r.json()
                self._token = payload.get("access_token")
                expires_in = int(payload.get("expires_in") or 1800)
                self._token_exp = time.time() + expires_in
                self.metrics["token_expires_in"] = expires_in
                log.info(
                    "[opensky] OAuth2 token acquired (expires_in=%ds)",
                    expires_in,
                )
                return self._token
            except Exception as exc:
                self.metrics["errors"] += 1
                self.metrics["last_error"] = f"token: {exc}"
                log.warning("[opensky] token fetch failed: %s", exc)
                return None

    # ------------------------------------------------------------------
    # Request helpers
    # ------------------------------------------------------------------

    def _build_states_request(
        self,
        bbox: tuple[float, float, float, float] | None,
    ) -> tuple[dict[str, str], dict[str, str], tuple[str, str] | None]:
        params: dict[str, str] = {}
        if bbox:
            lamin, lomin, lamax, lomax = bbox
            params = {
                "lamin": str(lamin),
                "lomin": str(lomin),
                "lamax": str(lamax),
                "lomax": str(lomax),
            }

        headers: dict[str, str] = {"User-Agent": USER_AGENT}
        auth: tuple[str, str] | None = None
        token = self.get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif self._legacy_user:
            auth = (self._legacy_user, self._legacy_pass)

        return params, headers, auth

    @staticmethod
    def _states_url(params: dict[str, str]) -> str:
        if not params:
            return STATES_URL
        return f"{STATES_URL}?{urlencode(params)}"

    @staticmethod
    def _spb_forward_headers(
        headers: dict[str, str],
        auth: tuple[str, str] | None,
    ) -> dict[str, str]:
        """Headers for ScrapingBee with forward_headers_pure (Spb- prefix)."""
        out: dict[str, str] = {"Spb-User-Agent": headers.get("User-Agent", USER_AGENT)}
        authz = headers.get("Authorization")
        if authz:
            out["Spb-Authorization"] = authz
        elif auth:
            raw = f"{auth[0]}:{auth[1]}".encode()
            out["Spb-Authorization"] = "Basic " + base64.b64encode(raw).decode()
        return out

    def _filter_state_vectors_by_bbox(
        self,
        states: list[list[Any]],
        bbox: tuple[float, float, float, float],
    ) -> list[list[Any]]:
        lamin, lomin, lamax, lomax = bbox
        out: list[list[Any]] = []
        for s in states:
            if not isinstance(s, list) or len(s) < 7:
                continue
            try:
                lonf = float(s[5])
                latf = float(s[6])
            except (TypeError, ValueError):
                continue
            if not (lamin <= latf <= lamax):
                continue
            if lomin <= lomax:
                if not (lomin <= lonf <= lomax):
                    continue
            else:
                if not (lonf >= lomin or lonf <= lomax):
                    continue
            out.append(s)
        return out

    def _fetch_states_scrapingbee(
        self,
        params: dict[str, str],
        headers: dict[str, str],
        auth: tuple[str, str] | None,
        *,
        force_sb: bool,
    ) -> dict[str, Any] | None:
        sb_key = self._scrapingbee_key()
        if not sb_key:
            return None

        if force_sb and not self._force_sb_mode_logged:
            log.info(
                "[opensky] using ScrapingBee proxy (forced via OPENSKY_USE_SCRAPINGBEE=1)"
            )
            self._force_sb_mode_logged = True

        target = self._states_url(params)
        query = (
            f"api_key={quote_plus(sb_key)}"
            f"&url={quote_plus(target)}"
            f"&render_js=false"
            f"&forward_headers_pure=true"
        )
        proxy_url = f"{SCRAPINGBEE_API}?{query}"
        spb_headers = self._spb_forward_headers(headers, auth)

        backoff = 2.0
        last_err = "no response"
        for attempt in range(2):
            self.metrics["scrapingbee_calls"] += 1
            try:
                r = requests.get(proxy_url, headers=spb_headers, timeout=30)
                if _scrapingbee_response_quota_exhausted(r):
                    self._scrapingbee_last_quota_hit = True
                if r.status_code == 200:
                    self._consecutive_429_direct = 0
                    try:
                        data = r.json()
                    except ValueError as exc:
                        last_err = f"invalid json: {exc}"
                        log.warning("[opensky] ScrapingBee body not JSON: %s", exc)
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    n = len(data.get("states") or [])
                    self.metrics["last_success_ts"] = int(time.time())
                    log.info(
                        "[opensky] ScrapingBee fetch OK — %d aircraft retrieved",
                        n,
                    )
                    return data
                last_err = f"http {r.status_code}"
                if r.status_code == 429:
                    log.warning(
                        "[opensky] ScrapingBee HTTP 429 (attempt %d/2)",
                        attempt + 1,
                    )
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                log.warning("[opensky] ScrapingBee HTTP %s", r.status_code)
                break
            except requests.exceptions.RequestException as exc:
                last_err = str(exc)
                log.warning(
                    "[opensky] ScrapingBee request failed (attempt %d/2): %s",
                    attempt + 1,
                    exc,
                )
                time.sleep(backoff)
                backoff *= 2

        self.metrics["scrapingbee_errors"] += 1
        self.metrics["last_error"] = f"scrapingbee: {last_err}"
        log.warning(
            "[opensky] ScrapingBee fetch failed: %s, falling back to direct",
            last_err,
        )
        return None

    def _fetch_states_direct(
        self,
        params: dict[str, str],
        headers: dict[str, str],
        auth: tuple[str, str] | None,
    ) -> dict[str, Any] | None:
        sb_key = self._scrapingbee_key()
        backoff = 2.0
        for attempt in range(3):
            self.metrics["calls"] += 1
            try:
                r = requests.get(
                    STATES_URL,
                    params=params or None,
                    headers=headers,
                    auth=auth,
                    timeout=15,
                )
                if r.status_code == 200:
                    self._consecutive_429_direct = 0
                    self._auto_sb_enabled = False
                    self.metrics["last_success_ts"] = int(time.time())
                    return r.json()
                if r.status_code == 429:
                    self.metrics["rate_limited"] += 1
                    prev = self._consecutive_429_direct
                    self._consecutive_429_direct += 1
                    if (
                        sb_key
                        and prev < CONSEC_429_SB_THRESHOLD
                        and self._consecutive_429_direct >= CONSEC_429_SB_THRESHOLD
                    ):
                        self._auto_sb_enabled = True
                        log.info(
                            "[opensky] auto-switch to ScrapingBee after %d consecutive 429s",
                            self._consecutive_429_direct,
                        )
                    log.warning(
                        "[opensky] 429 rate-limited (attempt %d/3)", attempt + 1
                    )
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                if r.status_code in (401, 403) and headers.get("Authorization"):
                    log.info("[opensky] %d on token, forcing refresh", r.status_code)
                    self._token = None
                    self._token_exp = 0.0
                    token = self.get_token()
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                    continue
                self.metrics["errors"] += 1
                self.metrics["last_error"] = f"http {r.status_code}"
                log.warning("[opensky] HTTP %d on /states/all", r.status_code)
                return None
            except requests.exceptions.RequestException as exc:
                self.metrics["errors"] += 1
                self.metrics["last_error"] = str(exc)
                log.warning("[opensky] request failed: %s", exc)
                time.sleep(backoff)
                backoff *= 2
        return None

    def _fetch_via_adsblol(
        self,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> dict[str, Any] | None:
        """Fetch global coverage via adsb.lol; return OpenSky-shaped {states, time}."""
        merged: dict[str, tuple[dict[str, Any], int]] = {}
        max_now = int(time.time())

        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {
                ex.submit(_fetch_adsblol_zone, lat, lon, dist, name): name
                for lat, lon, dist, name in ADSB_LOL_ZONES
            }
            for fut in as_completed(futs):
                zone_name = futs[fut]
                self.metrics["adsblol_calls"] += 1
                try:
                    _zname, ac_list, now_ts = fut.result()
                    max_now = max(max_now, now_ts)
                    for ac in ac_list:
                        if not isinstance(ac, dict):
                            continue
                        hx = (ac.get("hex") or "").lower().strip()
                        if not hx:
                            continue
                        if hx not in merged:
                            merged[hx] = (ac, now_ts)
                except Exception as exc:
                    self.metrics["adsblol_errors"] += 1
                    log.warning(
                        "[opensky] adsb.lol zone %s failed: %s", zone_name, exc
                    )

        if not merged:
            self.metrics["last_error"] = "adsblol: no aircraft"
            return None

        states: list[list[Any]] = []
        for _icao, (ac, znow) in merged.items():
            row = _ac_to_opensky_state(ac, znow)
            if row:
                states.append(row)

        if bbox:
            states = self._filter_state_vectors_by_bbox(states, bbox)

        if not states:
            self.metrics["last_error"] = "adsblol: empty after bbox filter"
            return None

        self.metrics["adsblol_used"] = True
        self.metrics["current_source"] = "adsblol"
        self.metrics["last_success_ts"] = int(time.time())
        log.info(
            "[opensky] adsb.lol fetch OK — %d aircraft retrieved across 10 zones",
            len(states),
        )
        return {"states": states, "time": max_now}

    # ------------------------------------------------------------------
    # States
    # ------------------------------------------------------------------

    def fetch_states(
        self, bbox: tuple[float, float, float, float] | None = None
    ) -> dict[str, Any] | None:
        """Fetch /api/states/all with backoff on 429.

        bbox: (lamin, lomin, lamax, lomax). When None, fetch global states.
        Returns: parsed JSON dict on success, None on permanent failure.
        """
        self._scrapingbee_last_quota_hit = False
        self.metrics["adsblol_used"] = False
        self.metrics["current_source"] = None

        if _truthy_env("OPENSKY_USE_ADSBLOL"):
            self.metrics["scrapingbee_used"] = False
            return self._fetch_via_adsblol(bbox)

        params, headers, auth = self._build_states_request(bbox)
        sb_key = self._scrapingbee_key()
        force_sb = _truthy_env("OPENSKY_USE_SCRAPINGBEE")
        self.metrics["scrapingbee_key_present"] = bool(sb_key)

        if force_sb and not sb_key:
            if not self._missing_sb_key_logged:
                log.warning(
                    "[opensky] OPENSKY_USE_SCRAPINGBEE=1 but SCRAPINGBEE_API_KEY "
                    "is missing; using direct OpenSky only"
                )
                self._missing_sb_key_logged = True

        prefer_sb = bool(sb_key and (force_sb or self._auto_sb_enabled))
        self.metrics["scrapingbee_used"] = prefer_sb

        if prefer_sb:
            self.metrics["current_source"] = "scrapingbee"
            data = self._fetch_states_scrapingbee(
                params, headers, auth, force_sb=force_sb
            )
            if data is not None:
                return data
            if not force_sb:
                self._auto_sb_enabled = False
            if self._scrapingbee_last_quota_hit:
                log.info(
                    "[opensky] Fallback to adsb.lol after ScrapingBee quota exceeded"
                )
            adsb = self._fetch_via_adsblol(bbox)
            if adsb is not None:
                return adsb
            return None

        self.metrics["current_source"] = "opensky_direct"
        data = self._fetch_states_direct(params, headers, auth)
        if data is not None:
            self.metrics["current_source"] = "opensky_direct"
            return data

        if sb_key:
            self.metrics["scrapingbee_used"] = True
            self.metrics["current_source"] = "scrapingbee"
            data = self._fetch_states_scrapingbee(
                params, headers, auth, force_sb=False
            )
            if data is not None:
                return data
            if self._scrapingbee_last_quota_hit:
                log.info(
                    "[opensky] Fallback to adsb.lol after ScrapingBee quota exceeded"
                )

        adsb = self._fetch_via_adsblol(bbox)
        if adsb is not None:
            return adsb
        return None


# Module-level singleton — one client per process.
_singleton: OpenSkyClient | None = None
_singleton_lock = threading.Lock()


def get_client() -> OpenSkyClient:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = OpenSkyClient()
    return _singleton
