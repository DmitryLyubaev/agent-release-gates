from pathlib import Path

from agent_release_gates.artifacts.store import digest


def allowance(root: Path, **overrides):
    config = {
        "allowance_id": "live-test",
        "study_id": "study-test",
        "project_root": str(root.resolve()),
        "ledger_path": str((root / ".local/live/live-test/budget.sqlite").resolve()),
        "provider": "anthropic",
        "model": "claude-sonnet-5-5",
        "price_id": "anthropic-global-2026-10-28",
        "input_nano_usd_per_token": 2000,
        "output_nano_usd_per_token": 10000,
        "cap_nano_usd": 10_000_000_000,
        "max_subject_attempts": 168,
        "max_judge_attempts": 96,
        "max_investigations": 28,
        "max_calibration_development": 8,
        "dataset_digest": "a" * 64,
    }
    config.update(overrides)
    return {
        "config": config,
        "config_digest": digest(config),
        "approved": True,
        "approved_by": "test-only-reviewer",
        "approved_at": "2026-10-28T00:00:00Z",
        "personal_account_confirmed": True,
        "budget_alert_ready": True,
        "allowed_stages": ["calibration"],
    }


def ledger(approval):
    from agent_release_gates.live.budget import BudgetLedger

    return BudgetLedger(Path(approval["config"]["ledger_path"]), approval)


def reserve(value, key="case-1-turn-0", **overrides):
    arguments = {
        "attempt_key": key,
        "kind": "subject",
        "investigation_id": "case-1",
        "metadata": {"stage": "calibration", "turn": 0, "case_id": "c01"},
    }
    arguments.update(overrides)
    return value.reserve(**arguments)
