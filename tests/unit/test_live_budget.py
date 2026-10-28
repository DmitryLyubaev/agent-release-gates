from copy import deepcopy
from pathlib import Path

import pytest

from tests.live_support import allowance, ledger, reserve


@pytest.mark.parametrize("details", [None, {"thinking_tokens": 0}, {"thinking_tokens": 3}])
def test_standard_usage_breakdown_preserves_receipt_without_double_charging(tmp_path, details):
    value = ledger(allowance(tmp_path))
    identity = reserve(value)
    usage = {
        "input_tokens": 100,
        "output_tokens": 10,
        "speed": "standard",
        "output_tokens_details": details,
    }
    value.settle(identity, usage, "req_current_standard")
    value.settle(identity, usage, "req_current_standard")
    summary = value.summary()
    assert summary["spent_nano_usd"] == 300_000
    assert summary["unsettled_calls"] == 0
    assert summary["calls"][0]["usage"] == usage


@pytest.mark.parametrize(
    "extra",
    [
        {"speed": "fast"},
        {"speed": "unknown"},
        {"speed": None},
        {"output_tokens_details": {"thinking_tokens": True}},
        {"output_tokens_details": {"thinking_tokens": 1.5}},
        {"output_tokens_details": {"thinking_tokens": -1}},
        {"output_tokens_details": {"thinking_tokens": 11}},
        {"output_tokens_details": {"thinking_tokens": 0, "unknown_tokens": 0}},
        {"output_tokens_details": {}},
        {"output_tokens_details": []},
    ],
)
def test_premium_speed_or_invalid_breakdown_keeps_reservation_unsettled(tmp_path, extra):
    value = ledger(allowance(tmp_path))
    identity = reserve(value)
    with pytest.raises(ValueError, match="USAGE"):
        value.settle(identity, {"input_tokens": 100, "output_tokens": 10, **extra}, "req_invalid")
    assert value.summary()["unsettled_calls"] == 1
    assert value.summary()["committed_nano_usd"] == 2_040_960_000


@pytest.mark.parametrize("field", ["approved", "personal_account_confirmed", "budget_alert_ready"])
def test_no_allowance_is_opened_without_explicit_readiness(tmp_path, field):
    approval = allowance(tmp_path)
    approval[field] = False
    with pytest.raises(ValueError, match="APPROVAL"):
        ledger(approval)
    assert not Path(approval["config"]["ledger_path"]).exists()


def test_known_receipt_replaces_reservation_once_and_replay_never_grants_send(tmp_path):
    approval = allowance(tmp_path)
    value = ledger(approval)
    identity = reserve(value)
    assert value.summary()["committed_nano_usd"] == 2_040_960_000
    usage = {"input_tokens": 100, "output_tokens": 10}
    value.settle(identity, usage, "req_test")
    value.settle(identity, usage, "req_test")
    assert value.summary()["spent_nano_usd"] == 300_000
    assert value.summary()["committed_nano_usd"] == 300_000
    with pytest.raises(ValueError, match="ATTEMPT"):
        reserve(ledger(approval))
    with pytest.raises(ValueError, match="USAGE_CONFLICT"):
        value.settle(identity, {"input_tokens": 101, "output_tokens": 10}, "req_test")


def test_pending_dispatch_survives_process_reopen_and_halts_all_further_spend(tmp_path):
    approval = allowance(tmp_path)
    reserve(ledger(approval))
    reopened = ledger(approval)
    assert reopened.summary()["unsettled_calls"] == 1
    assert reopened.summary()["committed_nano_usd"] == 2_040_960_000
    with pytest.raises(ValueError, match="UNSETTLED"):
        reserve(reopened, "other")


def test_judge_uses_its_output_bound_and_the_same_cumulative_cap(tmp_path):
    approval = allowance(tmp_path, cap_nano_usd=2_010_240_000)
    value = ledger(approval)
    identity = reserve(value, "judge", kind="judge", investigation_id=None)
    assert value.summary()["committed_nano_usd"] == 2_010_240_000
    value.settle(identity, {"input_tokens": 1, "output_tokens": 1}, "req_1")
    with pytest.raises(ValueError, match="BUDGET_LIMIT"):
        reserve(value, "judge2", kind="judge", investigation_id=None)


@pytest.mark.parametrize(
    "overrides", [{"input_nano_usd_per_token": 3000}, {"cap_nano_usd": 11_000_000_000}]
)
def test_repriced_or_increased_allowances_cannot_reopen_existing_spend(tmp_path, overrides):
    ledger(allowance(tmp_path))
    with pytest.raises(ValueError):
        ledger(allowance(tmp_path, **overrides))


def test_approval_digest_and_exact_canonical_path_bind_the_single_ledger(tmp_path):
    from agent_release_gates.live.budget import BudgetLedger

    approval = allowance(tmp_path)
    changed = deepcopy(approval)
    changed["config"]["cap_nano_usd"] = 1
    with pytest.raises(ValueError, match="APPROVAL"):
        ledger(changed)
    with pytest.raises(ValueError, match="LEDGER_PATH"):
        BudgetLedger(tmp_path / "another.sqlite", approval)


@pytest.mark.parametrize("suffix", ["payments-reconciliation-assistant", ".local/subject"])
def test_subject_checkouts_cannot_be_used_as_a_budget_root(tmp_path, suffix):
    with pytest.raises(ValueError, match="LEDGER_PATH"):
        ledger(allowance(tmp_path / suffix))


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": True, "output_tokens": 1},
        {"input_tokens": 1, "output_tokens": 4097},
        {"input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 1},
        {"input_tokens": 1, "output_tokens": 1, "server_tool_use": {"web_search_requests": 1}},
    ],
)
def test_unpriced_or_invalid_usage_is_never_treated_as_free(tmp_path, usage):
    value = ledger(allowance(tmp_path))
    identity = reserve(value)
    with pytest.raises(ValueError, match="USAGE"):
        value.settle(identity, usage, "req_bad")
    assert value.summary()["unsettled_calls"] == 1


def test_failed_attempts_and_new_investigations_use_persisted_count_limits(tmp_path):
    value = ledger(allowance(tmp_path, max_subject_attempts=1, max_investigations=1))
    identity = reserve(value)
    value.settle(identity, {"input_tokens": 1, "output_tokens": 1}, "req_count")
    with pytest.raises(ValueError, match="COUNT_LIMIT"):
        reserve(value, "next-turn")


def test_approval_for_calibration_cannot_dispatch_heldout(tmp_path):
    value = ledger(allowance(tmp_path))
    with pytest.raises(ValueError, match="STAGE"):
        reserve(value, metadata={"stage": "heldout", "turn": 0, "case_id": "h01"})
