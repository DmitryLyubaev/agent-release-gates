from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from langsmith.utils import LangSmithNotFoundError

from agent_release_gates.artifacts.store import digest
from agent_release_gates.contracts.artifacts import ArtifactBundle, Digest, StrictModel
from agent_release_gates.langsmith.local import LocalExperiment


class SyncPayload(StrictModel):
    identity_digest: Digest
    experiment_name: str
    dataset_name: str
    examples: list[dict]
    runs: list[dict]
    feedback: list[dict]


def uid(value):
    return str(uuid5(NAMESPACE_URL, value))


def build_sync_payload(experiment: LocalExperiment, bundles: list[ArtifactBundle]) -> SyncPayload:
    if (
        not bundles
        or len({b.manifest.dataset_digest for b in bundles}) != 1
        or len({b.manifest.subject_version for b in bundles}) != 1
    ):
        raise ValueError("ONE_VERSION_AND_DATASET_REQUIRED")
    identity = digest(
        {
            "experiment": experiment.model_dump(mode="json", exclude={"evaluator_elapsed_ms"}),
            "artifacts": [digest(b.model_dump(mode="json")) for b in bundles],
        }
    )
    runs, examples, feedback = [], [], []
    for bundle in bundles:
        manifest = bundle.manifest
        root_id = uid(identity + "/" + manifest.run_id)
        example_id = uid(manifest.dataset_digest + "/" + manifest.case_id)
        examples.append(
            {
                "id": example_id,
                "inputs": {
                    "case_id": manifest.case_id,
                    "evidence": bundle.documents.get("evidence"),
                },
            }
        )
        start = manifest.started_at.isoformat().replace("+00:00", "Z")
        end = manifest.ended_at.isoformat().replace("+00:00", "Z")
        order = datetime.fromisoformat(start).strftime("%Y%m%dT%H%M%S%fZ") + root_id
        root = {
            "id": root_id,
            "name": "captured-agent-run",
            "run_type": "chain",
            "start_time": start,
            "end_time": end,
            "inputs": {"evidence": bundle.documents.get("evidence")},
            "outputs": {
                "proposal": bundle.documents.get("proposal"),
                "capture": bundle.documents.get("capture"),
            },
            "parent_run_id": None,
            "trace_id": root_id,
            "dotted_order": order,
            "reference_example_id": example_id,
            "extra": {
                "metadata": {
                    "mode": manifest.mode,
                    "subject_version": manifest.subject_version,
                    "artifact_digest": digest(bundle.model_dump(mode="json")),
                    "usage": manifest.usage.model_dump(mode="json"),
                    "timing": "original_capture",
                }
            },
        }
        runs.append(root)
        requests = {}
        for event in bundle.documents.get("events", []):
            if event["kind"] == "model_request":
                requests[event["payload"]["turn"]] = event
            elif event["kind"] in ["model_response", "model_error", "tool_result", "tool_error"]:
                model = event["kind"].startswith("model_")
                request = requests.get(event["payload"].get("turn")) if model else None
                span_start = request["at"] if request else event["at"]
                child_id = uid(identity + "/" + manifest.run_id + "/" + str(event["seq"]))
                child_order = (
                    order
                    + "."
                    + datetime.fromisoformat(span_start).strftime("%Y%m%dT%H%M%S%fZ")
                    + child_id
                )
                runs.append(
                    {
                        "id": child_id,
                        "name": "captured-model-call"
                        if model
                        else event["payload"].get("name", "tool-observation"),
                        "run_type": "llm" if model else "tool",
                        "start_time": span_start,
                        "end_time": event["at"],
                        "inputs": request["payload"]
                        if request
                        else {"args": event["payload"].get("args")},
                        "outputs": event["payload"],
                        "parent_run_id": root_id,
                        "trace_id": root_id,
                        "dotted_order": child_order,
                        "extra": {
                            "metadata": {
                                "timing": "original_request_response"
                                if request
                                else "instantaneous_adapter_observation"
                            }
                        },
                    }
                )
        for row in experiment.rows:
            if row.get("run_id", row["item_id"]) != manifest.run_id:
                continue
            for key, score in row["scores"].items():
                if isinstance(score, (bool, int, float)):
                    feedback.append(
                        {
                            "id": uid(identity + "/" + manifest.run_id + "/" + key),
                            "run_id": root_id,
                            "key": key,
                            "score": score,
                        }
                    )
    return SyncPayload(
        identity_digest=identity,
        experiment_name="gates-" + bundles[0].manifest.subject_version + "-" + identity[:12],
        dataset_name="gates-" + bundles[0].manifest.dataset_digest[:16],
        examples=examples,
        runs=runs,
        feedback=feedback,
    )


class PostgresSyncRepository:
    def __init__(self, repository):
        self.repository = repository

    def reserve(self, identity):
        return self.repository.sync_state(identity, "reserve")

    def confirm(self, identity, remote_ids):
        self.repository.sync_state(identity, "confirm", remote_ids)

    def mark_unknown(self, identity):
        self.repository.sync_state(identity, "unknown")


def sync_experiment(payload: SyncPayload, sink, state) -> dict:
    identity = payload.identity_digest
    if sink.approved_payload_digest != identity:
        return {"state": "not_configured", "remote_ids": None}
    current = state.reserve(identity)
    if current["state"] == "confirmed":
        return {"state": "confirmed", "remote_ids": current["remote_ids"]}
    if current["state"] == "reserved" and not current.get("claimed", True):
        return {"state": "pending", "remote_ids": None}
    try:
        existing = sink.reconcile(payload)
        remote_ids = existing if existing is not None else sink.upload(payload)
    except Exception:  # noqa: BLE001 - remote outcome can be ambiguous; never retry the write here
        state.mark_unknown(identity)
        return {"state": "unknown", "remote_ids": None}
    state.confirm(identity, remote_ids)
    return {"state": "confirmed", "remote_ids": remote_ids}


class SdkLangSmithSink:
    """Explicitly configured sink. Never constructed by offline CLI/API defaults."""

    def __init__(self, client, approved_payload_digest: str | None = None):
        self.client = client
        self.approved_payload_digest = approved_payload_digest

    def _exists(self, reader, identity):
        try:
            return reader(identity)
        except LangSmithNotFoundError:
            return None

    def reconcile(self, payload):
        for run in payload.runs:
            if self._exists(self.client.read_run, run["id"]) is None:
                return None
        for feedback in payload.feedback:
            if self._exists(self.client.read_feedback, feedback["id"]) is None:
                return None
        return {"experiment": payload.experiment_name, "runs": [r["id"] for r in payload.runs]}

    def upload(self, payload):
        datasets = list(self.client.list_datasets(dataset_name=payload.dataset_name))
        if len(datasets) > 1:
            raise ValueError("AMBIGUOUS_REMOTE_DATASET")
        dataset = (
            datasets[0]
            if datasets
            else self.client.create_dataset(
                payload.dataset_name, description="Synthetic saved-run evidence"
            )
        )
        self.client.create_project(
            payload.experiment_name, reference_dataset_id=dataset.id, upsert=True
        )
        for example in payload.examples:
            existing = self._exists(self.client.read_example, example["id"])
            if existing is None:
                self.client.create_example(
                    dataset_id=dataset.id,
                    example_id=example["id"],
                    inputs=example["inputs"],
                    outputs={},
                )
            elif existing.inputs != example["inputs"]:
                raise ValueError("REMOTE_EXAMPLE_CONFLICT")
        for run in payload.runs:
            if self._exists(self.client.read_run, run["id"]) is None:
                self.client.create_run(**run, project_name=payload.experiment_name)
        for feedback in payload.feedback:
            if self._exists(self.client.read_feedback, feedback["id"]) is None:
                self.client.create_feedback(
                    run_id=feedback["run_id"],
                    key=feedback["key"],
                    score=feedback["score"],
                    feedback_id=feedback["id"],
                    stop_after_attempt=1,
                )
        return {"experiment": payload.experiment_name, "runs": [r["id"] for r in payload.runs]}
