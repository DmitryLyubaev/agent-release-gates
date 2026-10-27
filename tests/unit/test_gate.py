from copy import deepcopy

import pytest

from agent_release_gates.contracts.decisions import GateInput
from agent_release_gates.evaluation.gate import decide_release
from tests.support import gate_input


def decision(raw):
    return decide_release(GateInput.model_validate(raw)).status


def test_complete_qualified_four_case_candidate_accepted():
    assert decision(gate_input()) == "accept"


@pytest.mark.parametrize("qualification", ["pass", "fail", "inconclusive"])
def test_exact_failure_overrides_judge(qualification):
    raw = gate_input()
    raw["qualification"]["status"] = qualification
    raw["candidate"]["cases"][0]["exact"]["checks"]["money"] = "fail"
    assert decision(raw) == "reject"


@pytest.mark.parametrize(
    "fault",
    [
        "case",
        "baseline",
        "judge",
        "qualification",
        "usage",
        "manifest",
        "rubric",
        "duplicate",
        "mode",
    ],
)
def test_incomplete_or_incomparable_study_never_accepted(fault):
    raw = gate_input()
    if fault == "case":
        raw["candidate"]["cases"].pop()
    if fault == "baseline":
        raw["baseline"] = None
    if fault == "judge":
        raw["candidate"]["cases"][0]["judges"][0]["state"] = "abstained"
    if fault == "qualification":
        raw["qualification"]["status"] = "fail"
    if fault == "usage":
        raw["candidate"]["usage_complete"] = False
    if fault == "manifest":
        raw["candidate"]["manifest_digest"] = "e" * 64
    if fault == "rubric":
        raw["candidate"]["cases"][0]["judges"][0]["rubric_digest"] = "e" * 64
    if fault == "duplicate":
        raw["candidate"]["cases"][1] = deepcopy(raw["candidate"]["cases"][0])
    if fault == "mode":
        raw["candidate"]["mode"] = "live"
    assert decision(raw) == "inconclusive"


def test_only_qualified_judge_can_reject_semantics():
    raw = gate_input()
    raw["candidate"]["cases"][0]["judges"][0]["support"] = "no"
    assert decision(raw) == "reject"
    raw["qualification"]["status"] = "fail"
    assert decision(raw) == "inconclusive"
