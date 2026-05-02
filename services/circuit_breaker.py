"""Circuit breaker AstroScan — Backend Redis (etat partage entre workers).

3 etats : CLOSED (normal) -> OPEN (en panne) -> HALF_OPEN (test)

Migration vers Redis (CTO Phase 0 - Critique #2 PART 2/2 : Etat partage workers).

Usage :
    from services.circuit_breaker import CB_NASA
    result = CB_NASA.call(fetch_apod, fallback={"ok": False, "error": "circuit ouvert"})

Architecture Redis :
  - Cle "as:cb:<name>:state"     -> etat actuel (CLOSED/OPEN/HALF_OPEN)
  - Cle "as:cb:<name>:failures"  -> compteur d'echecs (TTL = recovery_timeout * 2)
  - Cle "as:cb:<name>:last_fail" -> timestamp dernier echec

Si un worker detecte une panne NASA -> tous les workers le savent immediatement.
Plus de comportement incoherent entre workers.
"""

import logging
import os
import time

log = logging.getLogger(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))

PREFIX_CB = "as:cb:"

_redis_client = None


def _get_redis():
    """Retourne le client Redis (lazy init, singleton par worker)."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis
            _redis_client = redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=2, socket_timeout=2,
            )
            _redis_client.ping()
        except Exception as e:
            log.error("[CB] Redis unavailable: %s", e)
            _redis_client = False
    return _redis_client if _redis_client else None


class CircuitBreaker:
    """Circuit breaker thread-safe + worker-shared via Redis."""

    def __init__(self, name, failure_threshold=5, recovery_timeout=60,
                 expected_exception=Exception):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self._key_state = PREFIX_CB + name + ":state"
        self._key_failures = PREFIX_CB + name + ":failures"
        self._key_last_fail = PREFIX_CB + name + ":last_fail"

    def _get_state_raw(self):
        c = _get_redis()
        if c is None:
            return "CLOSED"
        try:
            v = c.get(self._key_state)
            return v if v else "CLOSED"
        except Exception:
            return "CLOSED"

    def _set_state(self, state):
        c = _get_redis()
        if c is None:
            return
        try:
            c.set(self._key_state, state)
        except Exception as e:
            log.warning("[CB %s] set_state failed: %s", self.name, e)

    def _get_failures(self):
        c = _get_redis()
        if c is None:
            return 0
        try:
            v = c.get(self._key_failures)
            return int(v) if v else 0
        except Exception:
            return 0

    def _incr_failures(self):
        c = _get_redis()
        if c is None:
            return 0
        try:
            n = c.incr(self._key_failures)
            c.expire(self._key_failures, self.recovery_timeout * 2)
            return n
        except Exception as e:
            log.warning("[CB %s] incr_failures failed: %s", self.name, e)
            return 0

    def _reset_failures(self):
        c = _get_redis()
        if c is None:
            return
        try:
            c.delete(self._key_failures)
        except Exception:
            pass

    def _get_last_fail(self):
        c = _get_redis()
        if c is None:
            return None
        try:
            v = c.get(self._key_last_fail)
            return float(v) if v else None
        except Exception:
            return None

    def _set_last_fail(self, ts):
        c = _get_redis()
        if c is None:
            return
        try:
            c.setex(self._key_last_fail, self.recovery_timeout * 2, str(ts))
        except Exception:
            pass

    @property
    def state(self):
        current = self._get_state_raw()
        if current == "OPEN":
            last = self._get_last_fail()
            if last is not None and time.time() - last > self.recovery_timeout:
                self._set_state("HALF_OPEN")
                log.info("CircuitBreaker [%s] -> HALF_OPEN", self.name)
                return "HALF_OPEN"
        return current

    def call(self, fn, *args, fallback=None, **kwargs):
        """Appelle fn(*args, **kwargs). Retourne fallback si le circuit est OPEN."""
        if self.state == "OPEN":
            log.warning("CircuitBreaker [%s] OPEN -- fallback used", self.name)
            return fallback
        try:
            result = fn(*args, **kwargs)
            self._reset_failures()
            if self._get_state_raw() == "HALF_OPEN":
                self._set_state("CLOSED")
                log.info("CircuitBreaker [%s] -> CLOSED (recovered)", self.name)
            return result
        except self.expected_exception as e:
            n = self._incr_failures()
            self._set_last_fail(time.time())
            if n >= self.failure_threshold:
                self._set_state("OPEN")
                log.error("CircuitBreaker [%s] -> OPEN after %d failures: %s",
                          self.name, n, e)
            return fallback

    def reset(self):
        """Reinitialise manuellement le circuit breaker (admin)."""
        self._reset_failures()
        c = _get_redis()
        if c is not None:
            try:
                c.delete(self._key_state, self._key_last_fail)
            except Exception:
                pass
        log.info("CircuitBreaker [%s] reset -> CLOSED", self.name)

    def status(self):
        """Retourne un dict de statut pour l'API admin."""
        last = self._get_last_fail()
        return {
            "name": self.name,
            "state": self._get_state_raw(),
            "failures": self._get_failures(),
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_s": self.recovery_timeout,
            "last_failure_ago_s": (
                round(time.time() - last, 1) if last else None
            ),
        }


CB_NASA  = CircuitBreaker("NASA",   failure_threshold=3, recovery_timeout=300)
CB_N2YO  = CircuitBreaker("N2YO",   failure_threshold=3, recovery_timeout=120)
CB_NOAA  = CircuitBreaker("NOAA",   failure_threshold=5, recovery_timeout=180)
CB_ISS   = CircuitBreaker("ISS",    failure_threshold=5, recovery_timeout=60)
CB_METEO = CircuitBreaker("METEO",  failure_threshold=3, recovery_timeout=180)
CB_TLE   = CircuitBreaker("TLE",    failure_threshold=5, recovery_timeout=600)
CB_GROQ  = CircuitBreaker("GROQ",   failure_threshold=3, recovery_timeout=120)

ALL_BREAKERS = [CB_NASA, CB_N2YO, CB_NOAA, CB_ISS, CB_METEO, CB_TLE, CB_GROQ]


def all_status():
    """Retourne la liste de statut de tous les circuit breakers."""
    return [cb.status() for cb in ALL_BREAKERS]
