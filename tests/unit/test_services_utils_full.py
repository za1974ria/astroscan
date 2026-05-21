"""Unit tests — services.utils missing branches (PASS 4 backfill)."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from services import utils as su


pytestmark = pytest.mark.unit


# ── _parse_iso_to_epoch_seconds ──────────────────────────────────────────────


def test_parse_iso_z_suffix():
    epoch = su._parse_iso_to_epoch_seconds("2026-01-01T00:00:00Z")
    assert epoch == int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())


def test_parse_iso_with_offset():
    epoch = su._parse_iso_to_epoch_seconds("2026-01-01T01:00:00+01:00")
    assert epoch == int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())


def test_parse_iso_naive_assumes_utc():
    epoch = su._parse_iso_to_epoch_seconds("2026-01-01T00:00:00")
    assert epoch == int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())


def test_parse_iso_integer_passthrough():
    assert su._parse_iso_to_epoch_seconds(1735689600) == 1735689600


def test_parse_iso_float_passthrough():
    assert su._parse_iso_to_epoch_seconds(1735689600.5) == 1735689600


def test_parse_iso_none():
    assert su._parse_iso_to_epoch_seconds(None) is None


def test_parse_iso_empty():
    assert su._parse_iso_to_epoch_seconds("") is None


def test_parse_iso_garbage():
    assert su._parse_iso_to_epoch_seconds("not-a-date") is None


# ── _safe_json_loads — completeness ──────────────────────────────────────────


def test_safe_json_loads_dict():
    assert su._safe_json_loads('{"x": 1}') == {"x": 1}


def test_safe_json_loads_list():
    assert su._safe_json_loads("[1,2,3]") == [1, 2, 3]


def test_safe_json_loads_bytes_input():
    assert su._safe_json_loads(b'{"x": 1}') == {"x": 1}


def test_safe_json_loads_html_skipped():
    assert su._safe_json_loads("<html><body>nope</body></html>") is None


def test_safe_json_loads_log_label_branch():
    # Goes through the log.debug branch — must not raise.
    assert su._safe_json_loads('{"x:', log_label="test-label") is None


def test_safe_json_loads_too_short():
    assert su._safe_json_loads("x") is None


def test_safe_json_loads_undecodable_bytes_returns_none():
    """Bytes that don't decode as utf-8 strict — function uses errors='replace'."""
    # Even non-ascii high bytes should not raise.
    assert su._safe_json_loads(b"\xff\xfe\xfd") is None


# ── safe_ensure_dir ──────────────────────────────────────────────────────────


def test_safe_ensure_dir_creates_parent(tmp_path):
    target = tmp_path / "sub" / "deep" / "file.txt"
    su.safe_ensure_dir(str(target))
    assert (tmp_path / "sub" / "deep").is_dir()


def test_safe_ensure_dir_no_parent_is_safe():
    # Path with no parent dir component must not raise.
    su.safe_ensure_dir("file_only.txt")


def test_safe_ensure_dir_idempotent(tmp_path):
    target = tmp_path / "sub" / "file.txt"
    su.safe_ensure_dir(str(target))
    su.safe_ensure_dir(str(target))  # no-op


# ── _detect_lang ────────────────────────────────────────────────────────────


def test_detect_lang_english_text():
    text = "The image shows the bright star captured from the telescope."
    assert su._detect_lang(text) is True


def test_detect_lang_french_text():
    text = "L'image montre l'étoile brillante capturée depuis le télescope."
    assert su._detect_lang(text) is False


def test_detect_lang_too_short():
    assert su._detect_lang("Hi") is False


def test_detect_lang_empty():
    assert su._detect_lang("") is False


def test_detect_lang_none():
    assert su._detect_lang(None) is False


# ── _is_bot_user_agent — completeness ────────────────────────────────────────


@pytest.mark.parametrize(
    "ua",
    [
        "Googlebot/2.1",
        "bingbot/2.0",
        "AhrefsBot/7.0",
        "SemrushBot/6.0",
        "facebookexternalhit/1.1",
        "curl/7.81.0",
        "python-requests/2.28.0",
        "GPTBot/1.0",
        "ClaudeBot/1.0",
        "Bytespider",
    ],
)
def test_bot_detection_positives(ua):
    assert su._is_bot_user_agent(ua) is True


@pytest.mark.parametrize(
    "ua",
    [
        "Mozilla/5.0 (Windows NT 10.0) Chrome/120",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604",
        "",
        None,
    ],
)
def test_bot_detection_negatives(ua):
    assert su._is_bot_user_agent(ua) is False


def test_bot_detection_truncates_huge_ua():
    """Defense against UA-bomb DoS — function caps at 400 chars."""
    ua = "Mozilla/5.0 " + "x" * 10_000
    # Just must not hang / crash
    assert su._is_bot_user_agent(ua) is False
