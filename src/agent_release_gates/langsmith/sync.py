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
        if existing is None:
            if current["state"] == "unknown":
                return {"state": "unknown", "remote_ids": None}
            sink.upload(payload)
            existing = sink.reconcile(payload)
        if existing is None:
            raise RuntimeError("REMOTE_RECORDS_NOT_CONFIRMED")
        remote_ids = existing
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

    @classmethod
    def configured(cls, *, api_url, api_key, workspace_id, approved_payload_digest):
        if not approved_payload_digest:
            raise ValueError("HOSTED_NOT_CONFIGURED")
        from langsmith import Client
        from urllib3.util.retry import Retry

        class SingleWriteClient(Client):
            def request_with_retries(self, method, pathname, **kwargs):
                # The SDK has its own retry loop in addition to requests/urllib3.
                # In particular create_feedback otherwise requests ten attempts.
                if method.upper() != "GET":
                    kwargs["stop_after_attempt"] = 1
                return super().request_with_retries(method, pathname, **kwargs)

        client = SingleWriteClient(
            api_url=api_url,
            api_key=api_key,
            workspace_id=workspace_id,
            auto_batch_tracing=False,
            tracing_sampling_rate=1.0,
            omit_traced_runtime_info=True,
            tracing_mode="langsmith",
            retry_config=Retry(total=0, connect=0, read=0, redirect=0, status=0, other=0),
        )
        return cls(client, approved_payload_digest)

    def _exists(self, reader, identity):
        try:
            return reader(identity)
        except LangSmithNotFoundError:
            return None

    def reconcile(self, payload):
        def field(value, key):
            return value.get(key) if isinstance(value, dict) else getattr(value, key, None)

        datasets = list(self.client.list_datasets(dataset_name=payload.dataset_name))
        if len(datasets) != 1:
            return None
        dataset_id = str(datasets[0].id)
        project = self._exists(
            lambda name: self.client.read_project(project_name=name), payload.experiment_name
        )
        if project is None or str(field(project, "reference_dataset_id")) != dataset_id:
            return None
        project_id = str(field(project, "id"))
        for example in payload.examples:
            saved = self._exists(self.client.read_example, example["id"])
            if (
                saved is None
                or field(saved, "inputs") != example["inputs"]
                or str(field(saved, "dataset_id")) != dataset_id
            ):
                return None
        for run in payload.runs:
            saved = self._exists(self.client.read_run, run["id"])
            if saved is None or str(field(saved, "session_id")) != project_id:
                return None
            if any(
                field(saved, key) != run.get(key)
                for key in ["inputs", "outputs", "name", "run_type"]
            ):
                return None
            if any(
                str(field(saved, key)) != str(run.get(key))
                for key in ["parent_run_id", "trace_id", "reference_example_id"]
            ):
                return None
        for feedback in payload.feedback:
            saved = self._exists(self.client.read_feedback, feedback["id"])
            if (
                saved is None
                or any(field(saved, key) != feedback[key] for key in ["key", "score"])
                or str(field(saved, "run_id")) != feedback["run_id"]
            ):
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
        flush = getattr(self.client, "flush", None)
        if callable(flush):
            flush()
        return {"experiment": payload.experiment_name, "runs": [r["id"] for r in payload.runs]}
