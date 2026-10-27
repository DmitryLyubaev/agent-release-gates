from copy import deepcopy

import pytest

from agent_release_gates.artifacts.store import validate_bundle
from agent_release_gates.contracts.datasets import ExpectedCase
from agent_release_gates.contracts.decisions import GateInput
from agent_release_gates.evaluation.exact import check_exact
from agent_release_gates.evaluation.gate import decide_release
from tests.support import bundle, expected, gate_input, seal


def exact(raw, gold=None):
    return check_exact(validate_bundle(seal(raw)), ExpectedCase.model_validate(gold or expected()))


def test_missing_baseline_is_not_a_zero_score_comparator():
    raw = gate_input()
    for case in raw["baseline"]["cases"]:
        case["exact"]["checks"] = {k: "missing" for k in case["exact"]["checks"]}
    assert decide_release(GateInput.model_validate(raw)).status == "inconclusive"
    raw["candidate"]["cases"][0]["exact"]["checks"]["money"] = "fail"
    assert decide_release(GateInput.model_validate(raw)).status == "reject"


@pytest.mark.parametrize("decision", ["reject", "acknowledge"])
def test_explained_outcome_requires_an_accepting_review(decision):
    raw = bundle()
    for event in raw["documents"]["events"]:
        if event["kind"] in ["review_request", "review_replayed"]:
            event["payload"]["decision"] = decision
    assert exact(raw).checks["approval_boundary"] == "fail"


def test_replay_must_match_the_same_proposal_and_command():
    raw = bundle()
    event = next(e for e in raw["documents"]["events"] if e["kind"] == "review_replayed")
    event["payload"]["proposalId"] = "unrelated"
    assert exact(raw).checks["duplicate_review"] != "pass"


def test_stale_refusal_requires_matching_request_and_proposal_save():
    raw = bundle()
    request = deepcopy(
        next(e["payload"] for e in raw["documents"]["events"] if e["kind"] == "review_request")
    )
    raw["documents"]["events"] = [
        {
            "seq": 1,
            "at": raw["manifest"]["ended_at"],
            "kind": "review_refused",
            "payload": {**request, "code": "STALE"},
        },
        {
            "seq": 2,
            "at": raw["manifest"]["ended_at"],
            "kind": "capture_finished",
            "payload": {"complete": True, "status": "awaiting_review"},
        },
    ]
    gold = expected()
    gold.update(review_sequence="stale", outcome=None)
    assert exact(raw, gold).checks["stale_review"] == "missing"


def test_truncation_does_not_erase_an_observed_early_outcome():
    raw = bundle()
    events = raw["documents"]["events"]
    outcome = next(e for e in events if e["kind"] == "outcome")
    rest = [e for e in events if e["kind"] not in ["outcome", "capture_finished"]]
    raw["documents"]["events"] = [outcome, *rest]
    for n, event in enumerate(raw["documents"]["events"]):
        event.update(seq=n + 1, at=raw["manifest"]["started_at"])
    result = exact(raw)
    assert result.checks["complete"] == "missing"
    assert result.checks["approval_boundary"] == "fail"


@pytest.mark.parametrize(
    "field,value",
    [
        ("proposal", "not an object"),
        ("evidence", {"sources": "not a list", "policies": []}),
        ("final_sources", {}),
        ("capture", {"complete": "yes", "status": "completed", "error": None}),
    ],
)
def test_hash_valid_malformed_consumed_documents_are_rejected(field, value):
    raw = bundle()
    raw["documents"][field] = value
    with pytest.raises(ValueError):
        validate_bundle(seal(raw))


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"model": "", "prompt": "baseline", "prompt_digest": "a" * 64, "tools": "v1"},
        {"model": "scripted", "prompt": "baseline", "tools": "v1"},
    ],
)
def test_required_target_identity_is_not_optional(settings):
    raw = bundle()
    raw["manifest"]["settings"] = settings
    with pytest.raises(ValueError):
        validate_bundle(raw)
