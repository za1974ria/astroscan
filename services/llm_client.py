"""Low-level OpenAI client wrapper for AstroBrain (Session 1).

Design:
    - Thin wrapper around openai>=1.50 with explicit retries via tenacity.
    - Retries ONLY on transient errors (RateLimit, APIConnection, APITimeout).
    - NEVER retries on AuthenticationError / BadRequestError (would burn tokens).
    - Structured JSON logging to logs/astrobrain/llm_client.log.
    - Dry-run mode (LLM_DRY_RUN=1) returns stubbed response without API call —
      used in tests + when OPENAI_API_KEY is missing in production .env.
    - Never logs the API key.

Public surface:
    - LLMResponse dataclass
    - LLMClient class with .chat()
    - LLMClientError (raised only on misconfiguration, never on transient API failure)

Coexists with the existing Anthropic/Groq stack in app/services/ai_translate.py
without touching it.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# Resolve project root from this file location: <ROOT>/services/llm_client.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _PROJECT_ROOT / "logs" / "astrobrain"
_LOG_FILE = _LOG_DIR / "llm_client.log"


def _ensure_log_dir() -> bool:
    """Create the log dir if missing. Returns False silently if permission denied."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except (PermissionError, OSError) as exc:
        log.debug("[llm_client] log dir not writable (%s); falling back to stderr", exc)
        return False


def _log_jsonl(entry: dict) -> None:
    """Append a JSON line to the LLM client log. Best-effort, never raises."""
    if not _ensure_log_dir():
        return
    try:
        line = json.dumps(entry, default=str, ensure_ascii=False)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as exc:
        log.debug("[llm_client] log write failed: %s", exc)


@dataclass
class LLMResponse:
    """Standardized response envelope.

    Attributes:
        ok: True on a successful API call (or successful dry-run).
        text: Response text on success, None on failure.
        model: Model identifier actually used (may differ from requested on fallback).
        tokens_in: Estimated/reported input tokens.
        tokens_out: Reported output tokens.
        latency_ms: End-to-end call latency in milliseconds.
        error: Human-readable error short-message on failure (no provider details leaked).
        fallback: True when this response is a fallback (no API call, or all retries exhausted).
        attempts: Number of attempts made (1 on first success).
        dry_run: True when the response was generated in dry-run mode (no API call).
    """
    ok: bool
    text: str | None = None
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    error: str | None = None
    fallback: bool = False
    attempts: int = 0
    dry_run: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


class LLMClientError(Exception):
    """Raised on misconfiguration (NOT on transient API failure)."""


class LLMClient:
    """Thin OpenAI client with retries, structured logging, and dry-run mode.

    Construction:
        LLMClient(api_key=None, base_url=None, timeout=20.0)

    Configuration is resolved at construction time (NOT at call time) so a
    test can construct multiple clients side-by-side without leaking env state.
    """

    # Retry parameters — kept small to avoid burning the daily token budget on retries.
    MAX_ATTEMPTS = 3
    INITIAL_BACKOFF_SEC = 1.0
    MAX_BACKOFF_SEC = 4.0

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 20.0,
        dry_run: bool | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "").strip()
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL") or None
        self.timeout = timeout
        # Dry-run resolution: explicit arg > env var > absence of api_key
        if dry_run is None:
            env_dry = os.environ.get("LLM_DRY_RUN", "0").strip()
            self.dry_run = env_dry in ("1", "true", "True", "yes") or not self.api_key
        else:
            self.dry_run = bool(dry_run)

        if not self.dry_run and not self.api_key:
            # Should never happen given the dry-run fallback above, but be explicit.
            raise LLMClientError("OPENAI_API_KEY missing and dry_run is False")

        self._client = None  # Lazy: only instantiate openai client when not dry-run

    # ─── Internal: lazy openai client init ──────────────────────────────────

    def _get_openai(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI  # noqa: WPS433  — lazy import
        except ImportError as exc:
            raise LLMClientError(f"openai package missing: {exc}") from exc
        kwargs: dict[str, Any] = {"api_key": self.api_key, "timeout": self.timeout}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = OpenAI(**kwargs)
        return self._client

    # ─── Public API ─────────────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int = 1500,
        temperature: float = 0.2,
        extra: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Send a chat completion request. Returns LLMResponse — never raises on transient failures.

        Args:
            messages: OpenAI-format messages list [{"role": "...", "content": "..."}]
            model: Model identifier (e.g., "gpt-5-mini", "gpt-5", or a fallback like "gpt-4o-mini")
            max_tokens: Cap on output tokens (defense against runaway costs)
            temperature: Sampling temperature (lower = more deterministic; 0.2 is good for technical Q&A)
            extra: Optional extra fields forwarded to the OpenAI SDK (kept narrow)

        Returns:
            LLMResponse with ok/text/model/tokens/latency/error fields.
        """
        if self.dry_run:
            return self._dry_run_response(messages, model)

        from openai import (  # noqa: WPS433 — lazy
            APIConnectionError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            RateLimitError,
        )

        retriable = (RateLimitError, APIConnectionError, APITimeoutError)
        last_exc: Exception | None = None
        backoff = self.INITIAL_BACKOFF_SEC

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            t0 = time.monotonic()
            try:
                client = self._get_openai()
                payload: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "max_completion_tokens": max_tokens,
                }
                # temperature is optional — some GPT-5 family models reject custom values
                if temperature is not None:
                    payload["temperature"] = temperature
                if extra:
                    payload.update(extra)

                resp = client.chat.completions.create(**payload)
                latency_ms = int((time.monotonic() - t0) * 1000)

                text = ""
                if resp.choices and resp.choices[0].message:
                    text = resp.choices[0].message.content or ""

                usage = getattr(resp, "usage", None)
                tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
                tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
                model_used = getattr(resp, "model", model) or model

                result = LLMResponse(
                    ok=True,
                    text=text,
                    model=model_used,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                    attempts=attempt,
                )
                _log_jsonl({
                    "ts": _iso_now(),
                    "level": "info",
                    "model": model_used,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "latency_ms": latency_ms,
                    "status": "ok",
                    "attempts": attempt,
                })
                return result

            except retriable as exc:
                last_exc = exc
                latency_ms = int((time.monotonic() - t0) * 1000)
                _log_jsonl({
                    "ts": _iso_now(),
                    "level": "warn",
                    "model": model,
                    "latency_ms": latency_ms,
                    "status": "retriable_error",
                    "exc_type": type(exc).__name__,
                    "attempt": attempt,
                })
                if attempt < self.MAX_ATTEMPTS:
                    time.sleep(min(backoff, self.MAX_BACKOFF_SEC))
                    backoff = min(backoff * 2, self.MAX_BACKOFF_SEC)
                    continue

            except (AuthenticationError, BadRequestError) as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                # NEVER log the exception's message verbatim — it can contain
                # the API key in some OpenAI error variants. Log only type + short class name.
                _log_jsonl({
                    "ts": _iso_now(),
                    "level": "error",
                    "model": model,
                    "latency_ms": latency_ms,
                    "status": "non_retriable_error",
                    "exc_type": type(exc).__name__,
                    "attempt": attempt,
                })
                return LLMResponse(
                    ok=False,
                    text=None,
                    model=model,
                    latency_ms=latency_ms,
                    error=_safe_error_message(exc),
                    fallback=True,
                    attempts=attempt,
                )

            except Exception as exc:  # noqa: BLE001 — defensive catch-all
                latency_ms = int((time.monotonic() - t0) * 1000)
                last_exc = exc
                _log_jsonl({
                    "ts": _iso_now(),
                    "level": "error",
                    "model": model,
                    "latency_ms": latency_ms,
                    "status": "unexpected_error",
                    "exc_type": type(exc).__name__,
                    "attempt": attempt,
                })
                # Defensive: don't retry on unknown exception classes.
                break

        # All retries exhausted (or unexpected error).
        return LLMResponse(
            ok=False,
            text=None,
            model=model,
            error=_safe_error_message(last_exc) if last_exc else "unknown_error",
            fallback=True,
            attempts=self.MAX_ATTEMPTS,
        )

    # ─── Helpers ───────────────────────────────────────────────────────────

    def _dry_run_response(self, messages: list[dict[str, str]], model: str) -> LLMResponse:
        """Return a stubbed response without contacting the API. For tests + CI + no-key prod."""
        prompt_chars = sum(len(m.get("content") or "") for m in messages)
        text = (
            "[DRY_RUN] AstroBrain LLM call simulated. "
            f"Model requested: {model}. Prompt total chars: {prompt_chars}. "
            "Set LLM_DRY_RUN=0 and provide OPENAI_API_KEY to use a real model."
        )
        return LLMResponse(
            ok=True,
            text=text,
            model=f"{model}-dry-run",
            tokens_in=max(1, prompt_chars // 4),  # ~4 chars/token; floor at 1
            tokens_out=max(1, len(text) // 4),
            latency_ms=0,
            dry_run=True,
            attempts=1,
        )


# ─── Module-level utilities ─────────────────────────────────────────────────


def _iso_now() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat()


def _safe_error_message(exc: BaseException | None) -> str:
    """Produce a short, leak-safe error message (no API key, no provider URLs, no request IDs)."""
    if exc is None:
        return "unknown_error"
    name = type(exc).__name__
    # Map by class name to friendly category — avoid str(exc) which can contain secrets.
    mapping = {
        "RateLimitError": "rate_limited",
        "APIConnectionError": "connection_error",
        "APITimeoutError": "timeout",
        "AuthenticationError": "auth_error",
        "BadRequestError": "bad_request",
    }
    return mapping.get(name, "upstream_error")


def make_default_client() -> LLMClient:
    """Convenience factory using process env vars. May enter dry-run automatically."""
    return LLMClient()


__all__ = [
    "LLMClient",
    "LLMClientError",
    "LLMResponse",
    "make_default_client",
]
