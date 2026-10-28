from copy import deepcopy

import pytest

from agent_release_gates.contracts.decisions import GateInput
from agent_release_gates.contracts.labels import HumanLabel
from agent_release_gates.evaluation.gate import decide_release
from agent_release_gates.evaluation.qualification import qualify
from tests.support import gate_input, qualification_fixture


def assistant_fixture():
    from agent_release_gates.contracts.artifacts import Usage
    from agent_release_gates.contracts.labels import ReviewLabel

    labels, results, manifest = qualification_fixture()
    labels = [
        ReviewLabel.model_validate({**row.model_dump(mode="json"), "provenance": "assistant"})
        for row in labels
    ]
    usage = Usage(
        state="known",
        input_tokens=1,
        output_tokens=1,
        cost_nano_usd=12000,
        reserved_nano_usd=0,
        price_id="test-only",
    )
    results = [
        row.model_copy(update={"mode": "live", "usage": usage, "receipt_digest": "a" * 64})
        for row in results
    ]
    return labels, results, manifest


def test_generic_assistant_labels_do_not_broaden_strict_human_contract():
    labels, _, _ = assistant_fixture()
    assert labels[0].provenance == "assistant"
    with pytest.raises(ValueError):
        HumanLabel.model_validate(labels[0].model_dump(mode="json"))


def test_assistant_qualification_is_explicit_and_uses_reference_metrics():
    labels, results, manifest = assistant_fixture()
    value = qualify(labels, results, manifest)
    assert value.status == "pass" and value.study_mode == "assistant_live"
    assert value.metrics[0]["reference_acceptable"] == 8
    assert value.metrics[0]["reference_provenance"] == "assistant"
    assert "human_acceptable" not in value.metrics[0]


@pytest.mark.parametrize("fault", ["mixed_reference", "scripted_judge", "unknown_usage"])
def test_assistant_qualification_cannot_launder_mixed_or_unsettled_evidence(fault):
    labels, results, manifest = assistant_fixture()
    if fault == "mixed_reference":
        labels[0] = labels[0].model_copy(update={"provenance": "human"})
    elif fault == "scripted_judge":
        results = [row.model_copy(update={"mode": "scripted"}) for row in results]
    else:
        usage = results[0].usage.model_copy(
            update={"state": "unknown", "cost_nano_usd": None, "reserved_nano_usd": 2010240000}
        )
        results[0] = results[0].model_copy(update={"usage": usage})
    value = qualify(labels, results, manifest)
    assert value.status == "inconclusive" and value.study_mode != "human_live"


def assistant_gate():
    raw = deepcopy(gate_input())
    raw["qualification"]["study_mode"] = "assistant_live"
    for key in ["baseline", "candidate"]:
        raw[key]["mode"] = "live"
        for case in raw[key]["cases"]:
            for judge in case["judges"]:
                judge["mode"] = "live"
    return raw


def test_default_human_gate_refuses_assistant_qualification_and_keeps_legacy_serialization():
    raw = assistant_gate()
    value = GateInput.model_validate(raw)
    assert "review_mode" not in value.model_dump(mode="json")
    assert decide_release(value).status == "inconclusive"
    raw["review_mode"] = "assistant"
    explicit = GateInput.model_validate(raw)
    assert explicit.model_dump(mode="json")["review_mode"] == "assistant"
    assert decide_release(explicit).status == "accept"
    raw["candidate"]["cases"][0]["exact"]["checks"]["money"] = "fail"
    assert decide_release(GateInput.model_validate(raw)).reason_codes == ["EXACT_VIOLATION"]


def test_assistant_policy_cannot_use_a_human_qualification():
    raw = assistant_gate()
    raw.update(review_mode="assistant")
    raw["qualification"]["study_mode"] = "human_live"
    assert decide_release(GateInput.model_validate(raw)).status == "inconclusive"
