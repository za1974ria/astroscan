"""Smoke test for the MockAdapter. Runs on any OS, no network."""
from __future__ import annotations

from astroscan_bridge.adapters.base import (
    READ_PROPERTIES_BY_KIND,
    AbstractReadOnlyAdapter,
)
from astroscan_bridge.adapters.mock import MockAdapter


def test_mock_discover_returns_three_devices():
    a = MockAdapter()
    devs = a.discover()
    kinds = sorted(d.kind for d in devs)
    assert kinds == ["camera", "focuser", "mount"]


def test_mock_telemetry_shape():
    a = MockAdapter()
    for d in a.discover():
        s = a.read_device(d.device_local_id)
        assert s.kind == d.kind
        assert "is_connected" in s.fields
        # No motion-verb keys should leak into the public fields.
        for k in s.fields:
            low = k.lower()
            assert "slew" not in low or low == "is_slewing"
            assert "park" not in low or low.startswith("is_park")
            assert "goto" not in low
            assert "pulse" not in low
            assert "sync" not in low
            assert "motor" not in low


def test_mock_adapter_is_subclass_of_abstract_readonly():
    assert issubclass(MockAdapter, AbstractReadOnlyAdapter)


def test_no_extra_public_methods():
    """Concrete adapters must not add public methods beyond the base."""
    base_public = {
        n for n in dir(AbstractReadOnlyAdapter)
        if not n.startswith("_")
    }
    extras = {
        n for n in dir(MockAdapter)
        if not n.startswith("_") and n not in base_public
    }
    # `driver_name` class attribute is part of the contract.
    extras.discard("driver_name")
    assert not extras, f"MockAdapter exposes extra public symbols: {extras}"


def test_allowlist_kinds_match_descriptors():
    a = MockAdapter()
    for d in a.discover():
        # Every reported kind must have a read-only property allow-list.
        assert d.kind in READ_PROPERTIES_BY_KIND, d.kind
