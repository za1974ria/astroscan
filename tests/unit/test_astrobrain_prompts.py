"""Unit tests — AstroBrain prompts (presence + char-cap)."""

from __future__ import annotations

import pytest

from app.blueprints.astrobrain import prompts

pytestmark = pytest.mark.unit


REQUIRED_PROMPTS = [
    "MISSION_ASSISTANT",
    "TELEMETRY_EXPLAINER",
    "HEALTH_SUMMARIZER",
    "ANOMALY_ANALYZER",
]


@pytest.mark.parametrize("name", REQUIRED_PROMPTS)
def test_prompt_present_and_string(name):
    val = getattr(prompts, name)
    assert isinstance(val, str)
    assert len(val) > 50, f"{name} is too short — likely a placeholder"


@pytest.mark.parametrize("name", REQUIRED_PROMPTS)
def test_prompt_under_char_cap(name):
    val = getattr(prompts, name)
    assert len(val) < prompts.MAX_PROMPT_CHARS, (
        f"{name} exceeds MAX_PROMPT_CHARS ({len(val)} >= {prompts.MAX_PROMPT_CHARS})"
    )


def test_prompts_dict_contains_all_four():
    assert set(prompts.PROMPTS.keys()) == {
        "mission_assistant",
        "telemetry_explainer",
        "health_summarizer",
        "anomaly_analyzer",
    }


def test_all_prompts_in_english():
    """Prompts target ESA/NASA/CNES audience — must be English (heuristic)."""
    english_signals = ("you", "the", "and")
    for name, val in prompts.PROMPTS.items():
        lower = val.lower()
        hits = sum(1 for w in english_signals if f" {w} " in f" {lower} ")
        assert hits >= 2, f"prompt {name} doesn't look English-dominant"


def test_no_prompt_leaks_secret_format():
    """Defense against accidental copy-paste of secrets into prompts."""
    forbidden = ("sk-", "Bearer ", "openai_api_key=", "ANTHROPIC_API_KEY")
    for name, val in prompts.PROMPTS.items():
        for f in forbidden:
            assert f not in val, f"prompt {name} contains suspicious token-like substring: {f}"
