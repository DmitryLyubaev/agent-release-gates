from copy import deepcopy

import pytest

from agent_release_gates.artifacts.store import validate_bundle
from agent_release_gates.contracts.datasets import ExpectedCase
from agent_release_gates.evaluation.exact import check_exact
from tests.support import bundle, expected, seal


def checked(raw):
    return check_exact(validate_bundle(seal(raw)), ExpectedCase.model_validate(expected()))


def test_exact_contract_passes():
    assert checked(bundle()).passed


@pytest.mark.parametrize(
    "fault,check",
    [
        ("money", "money"),
        ("category", "category"),
        ("ref", "references"),
        ("version", "references"),
        ("original", "originals"),
        ("early", "approval_boundary"),
        ("duplicate", "outcome"),
    ],
)
def test_exact_failures_cannot_be_rescued_by_claimed_safe_flag(fault, check):
    raw = bundle()
    docs = raw["documents"]
    if fault == "money":
        docs["proposal"]["differenceMinor"] = "100"
    if fault == "category":
        docs["proposal"]["category"] = "unexplained_mismatch"
    if fault == "ref":
        docs["proposal"]["evidenceRefs"].pop()
    if fault == "version":
        docs["proposal"]["evidenceRefs"][0]["version"] = 2
    if fault == "original":
        docs["final_sources"][0]["grossMinor"] = "0"
    if fault == "early":
        index = next(n for n, e in enumerate(docs["events"]) if e["kind"] == "outcome")
        docs["events"][0], docs["events"][index] = docs["events"][index], docs["events"][0]
        for n, event in enumerate(docs["events"]):
            event.update(seq=n + 1, at=raw["manifest"]["started_at"])
    if fault == "duplicate":
        docs["events"].insert(-1, deepcopy(docs["events"][-2]))
        for n, event in enumerate(docs["events"]):
            event["seq"] = n + 1
    docs["capture"]["safe"] = True
    result = checked(raw)
    assert result.checks[check] == "fail"
    assert not result.passed


def test_truncated_event_evidence_is_missing():
    raw = bundle()
    raw["documents"]["events"] = []
    result = checked(raw)
    assert result.checks["complete"] == "missing"
    assert result.checks["approval_boundary"] == "missing"


def test_stale_approval_is_not_accepted():
    gold = expected()
    gold.update(review_sequence="stale", outcome=None)
    result = check_exact(validate_bundle(bundle()), ExpectedCase.model_validate(gold))
    assert result.checks["stale_review"] == "fail"
