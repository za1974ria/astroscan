"""AstroBrainService — business layer between the blueprint routes and the
low-level services.llm_client.

Responsibilities:
    - Pick the right model (default vs premium) per method.
    - Estimate token usage and gate calls through rate_limit.check_budget().
    - Stitch system prompt + user payload + optional context.
    - Always return a uniform dict envelope — callers (routes) don't see
      LLMResponse directly.

This layer is the ONLY place where business rules live. Routes are I/O
glue, llm_client is provider glue, prompts.py is content. Keep service.py
the brain.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from app.blueprints.astrobrain import prompts, rate_limit
from services.llm_client import LLMClient, LLMResponse

log = logging.getLogger(__name__)


def _model_default() -> str:
    return (os.environ.get("ASTROBRAIN_MODEL_DEFAULT") or "gpt-5-mini").strip()


def _model_premium() -> str:
    return (os.environ.get("ASTROBRAIN_MODEL_PREMIUM") or "gpt-5").strip()


def _estimate_tokens(messages: list[dict[str, str]]) -> int:
    """Rough token estimate (~4 chars per token) for budget check before the call.
    Intentionally conservative-ish; we record the real usage after the call."""
    chars = sum(len(m.get("content") or "") for m in messages)
    return max(1, chars // 4)


def _envelope(resp: LLMResponse, *, extra: dict[str, Any] | None = None) -> dict:
    """Normalize the LLMResponse into the public dict envelope returned by all methods."""
    out: dict[str, Any] = {
        "ok": bool(resp.ok),
        "answer": resp.text,
        "model": resp.model,
        "tokens": {"in": resp.tokens_in, "out": resp.tokens_out},
        "latency_ms": resp.latency_ms,
        "attempts": resp.attempts,
        "dry_run": resp.dry_run,
        "error": resp.error,
    }
    if extra:
        out.update(extra)
    return out


class AstroBrainService:
    """High-level orchestrator. Stateless except for the underlying LLMClient."""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    # ─── Public methods ────────────────────────────────────────────────────

    def ask(self, question: str, context: dict | None = None) -> dict:
        """Free-form Q&A. Defaults to the cheap model."""
        if not isinstance(question, str) or not question.strip():
            return {"ok": False, "error": "question_required", "answer": None}
        user_content = question.strip()
        if context:
            try:
                user_content += "\n\nContext:\n" + json.dumps(context, ensure_ascii=False)[:2000]
            except (TypeError, ValueError):
                pass

        messages = [
            {"role": "system", "content": prompts.MISSION_ASSISTANT},
            {"role": "user", "content": user_content},
        ]
        return self._dispatch(messages, model=_model_default(), method="ask")

    def explain_telemetry(self, telemetry: dict, focus: str | None = None) -> dict:
        """Interpret a telemetry JSON snapshot. Uses the premium model by default."""
        if not isinstance(telemetry, dict) or not telemetry:
            return {"ok": False, "error": "telemetry_required", "answer": None}
        payload = {"telemetry": telemetry}
        if focus:
            payload["focus"] = str(focus)[:200]
        messages = [
            {"role": "system", "content": prompts.TELEMETRY_EXPLAINER},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)[:3500]},
        ]
        return self._dispatch(messages, model=_model_premium(), method="explain_telemetry")

    def summarize_health(self, health_data: dict) -> dict:
        """Short natural-language status banner from a Guardian snapshot."""
        if not isinstance(health_data, dict) or not health_data:
            return {"ok": False, "error": "health_data_required", "answer": None}
        messages = [
            {"role": "system", "content": prompts.HEALTH_SUMMARIZER},
            {"role": "user", "content": json.dumps(health_data, ensure_ascii=False)[:3000]},
        ]
        return self._dispatch(messages, model=_model_default(), method="summarize_health")

    def analyze_anomaly(self, logs_excerpt: str, metrics: dict | None = None) -> dict:
        """Three-line root-cause guess from logs + metrics. Uses default model."""
        payload = {"logs": (logs_excerpt or "")[:2500]}
        if metrics:
            payload["metrics"] = metrics
        messages = [
            {"role": "system", "content": prompts.ANOMALY_ANALYZER},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)[:3500]},
        ]
        return self._dispatch(messages, model=_model_default(), method="analyze_anomaly")

    # ─── Internal dispatch ─────────────────────────────────────────────────

    def _dispatch(
        self,
        messages: list[dict[str, str]],
        model: str,
        method: str,
        max_tokens: int = 2000,
    ) -> dict:
        estimated = _estimate_tokens(messages)
        ok, remaining, snapshot = rate_limit.check_budget(estimated)
        if not ok:
            log.warning(
                "[astrobrain] budget exceeded — method=%s estimated=%d remaining=%d",
                method,
                estimated,
                remaining,
            )
            return {
                "ok": False,
                "error": "daily_token_budget_exceeded",
                "answer": None,
                "model": model,
                "tokens": {"in": 0, "out": 0},
                "budget": snapshot,
            }

        resp = self.client.chat(messages, model=model, max_tokens=max_tokens, temperature=0.2)

        # Record real usage (or estimate if upstream didn't return one).
        total = (resp.tokens_in or 0) + (resp.tokens_out or 0)
        if total == 0:
            total = estimated
        rate_limit.record_usage(total)

        return _envelope(resp, extra={"method": method})


__all__ = ["AstroBrainService"]
