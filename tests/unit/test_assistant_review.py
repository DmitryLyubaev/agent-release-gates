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


@pytest.mark.parametrize("provenance", ["assistant", "human"])
def test_dangerous_unsafe_next_step_counts_even_with_supported_explanation(provenance):
    labels, results, manifest = assistant_fixture()
    labels = [row.model_copy(update={"provenance": provenance}) for row in labels]
    labels = [
        row.model_copy(update={"support": "yes", "usefulness": "no"})
        if row.item_id == "item_12"
        else row
        for row in labels
    ]
    results = [
        row.model_copy(update={"support": "yes", "usefulness": "no"})
        if row.item_id == "item_12"
        else row
        for row in results
    ]
    assert qualify(labels, results, manifest).status == "pass"
    results = [
        row.model_copy(update={"usefulness": "yes"})
        if row.item_id == "item_12" and row.repetition == 1
        else row
        for row in results
    ]
    value = qualify(labels, results, manifest)
    assert value.status == "fail"
    assert value.metrics[0]["dangerous_false_accepts"] == 1


def sync_payload(reference=None):
    from agent_release_gates.artifacts.store import validate_bundle
    from agent_release_gates.langsmith.local import LocalExperiment
    from agent_release_gates.langsmith.sync import build_sync_payload
    from tests.support import bundle

    artifact = validate_bundle(bundle())
    experiment = LocalExperiment(
        identity_digest="f" * 64,
        rows=[{"item_id": artifact.manifest.run_id, "scores": {"supported": 1}}],
        evaluator_elapsed_ms=1,
        mode="local_no_upload",
    )
    return build_sync_payload(experiment, [artifact], reference_provenance=reference)


def test_sync_identity_and_root_metadata_bind_assistant_provenance():
    legacy = sync_payload()
    explicit = sync_payload("assistant")
    assert legacy.identity_digest != explicit.identity_digest
    root = next(row for row in explicit.runs if row["parent_run_id"] is None)
    assert root["extra"]["metadata"]["reference_provenance"] == "assistant"
    assert root["extra"]["metadata"]["human_validation"] is False
    assert "reference_provenance" not in legacy.runs[0]["extra"]["metadata"]
    with pytest.raises(ValueError, match="PROVENANCE"):
        sync_payload("pretend_human")


def test_new_assistant_packet_template_does_not_claim_human_labels(tmp_path):
    import json

    from agent_release_gates.review.packet import export_packet
    from tests.unit.test_review import item

    export_packet(
        [item(source_mode="live")], "calibration", tmp_path, reference_provenance="assistant"
    )
    row = json.loads((tmp_path / "labels-template.json").read_bytes())[0]
    assert row["provenance"] == "assistant" and row["support"] is None


def test_assistant_report_discloses_unmeasured_human_agreement():
    from agent_release_gates.evaluation.report import report_metrics
    from tests.support import bundle

    raw = assistant_gate()
    raw["review_mode"] = "assistant"
    manifests = {
        case["run_id"]: bundle()["manifest"]
        for key in ["baseline", "candidate"]
        for case in raw[key]["cases"]
    }
    report = report_metrics(raw, manifests)
    assert report["review_mode"] == report["reference_provenance"] == "assistant"
    assert report["human_validation"] is False
    assert "assistant" in report["scope"]


def test_remote_readback_must_confirm_reference_provenance_metadata():
    from types import SimpleNamespace

    from agent_release_gates.langsmith.sync import SdkLangSmithSink
    from tests.unit.test_langsmith_sync import payload

    data = payload()
    data.runs[0]["extra"]["metadata"].update(
        reference_provenance="assistant", human_validation=False
    )

    class Destination:
        def list_datasets(self, **kwargs):
            return [SimpleNamespace(id="dataset")]

        def read_project(self, **kwargs):
            return SimpleNamespace(id="project", reference_dataset_id="dataset")

        def read_example(self, identity):
            return SimpleNamespace(
                inputs=next(row["inputs"] for row in data.examples if row["id"] == identity),
                dataset_id="dataset",
            )

        def read_run(self, identity):
            row = deepcopy(next(row for row in data.runs if row["id"] == identity))
            if row["parent_run_id"] is None:
                row["extra"]["metadata"]["human_validation"] = True
            return SimpleNamespace(**row, session_id="project")

        def read_feedback(self, identity):
            return SimpleNamespace(**next(row for row in data.feedback if row["id"] == identity))

    assert SdkLangSmithSink(Destination(), data.identity_digest).reconcile(data) is None
