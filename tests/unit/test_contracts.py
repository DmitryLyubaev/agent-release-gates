import pytest
from pydantic import TypeAdapter

from agent_release_gates.artifacts.store import validate_bundle
from agent_release_gates.contracts.artifacts import Money
from tests.support import bundle


def test_large_amount_survives_and_float_is_refused():
    money = TypeAdapter(Money)
    assert money.validate_python("9007199254740993") == "9007199254740993"
    for bad in [1.1, 1, "01", "1.0", "-1"]:
        with pytest.raises(ValueError):
            money.validate_python(bad)


def test_non_utc_and_unknown_fields_refused():
    raw = bundle()
    raw["manifest"]["started_at"] = "2026-10-27T10:00:00+10:00"
    with pytest.raises(ValueError):
        validate_bundle(raw)
    raw = bundle()
    raw["manifest"]["trust_me"] = True
    with pytest.raises(ValueError):
        validate_bundle(raw)


def test_unknown_live_cost_never_becomes_zero():
    raw = bundle(mode="live")
    raw["manifest"]["usage"].update(state="unknown", cost_nano_usd=0, reserved_nano_usd=1)
    with pytest.raises(ValueError):
        validate_bundle(raw)
