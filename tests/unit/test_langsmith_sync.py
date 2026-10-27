from agent_release_gates.artifacts.store import validate_bundle
from agent_release_gates.langsmith.local import LocalExperiment
from agent_release_gates.langsmith.sync import build_sync_payload, sync_experiment
from tests.support import bundle


class MemoryState:
    def __init__(self):
        self.value = None

    def reserve(self, identity):
        if self.value is None:
            self.value = {"state": "reserved", "remote_ids": None}
            return {**self.value, "claimed": True}
        return {**self.value, "claimed": False}

    def confirm(self, identity, remote_ids):
        self.value = {"state": "confirmed", "remote_ids": remote_ids}

    def mark_unknown(self, identity):
        self.value = {"state": "unknown", "remote_ids": None}


class FakeDestination:
    def __init__(self, payload, ambiguous=False):
        self.approved_payload_digest = payload.identity_digest
        self.saved = None
        self.ambiguous = ambiguous
        self.uploads = 0

    def reconcile(self, payload):
        return self.saved

    def upload(self, payload):
        self.uploads += 1
        self.saved = {
            "experiment": payload.experiment_name,
            "runs": [r["id"] for r in payload.runs],
        }
        if self.ambiguous:
            raise TimeoutError("Maybe accepted")
        return self.saved


def payload():
    raw = bundle()
    raw["documents"]["events"][0]["kind"] = "model_request"
    raw["documents"]["events"][0]["payload"] = {
        "turn": 0,
        "messages": [{"role": "user", "text": "synthetic"}],
    }
    raw["documents"]["events"][1]["kind"] = "model_response"
    raw["documents"]["events"][1]["payload"] = {
        "turn": 0,
        "reply": {"type": "proposal", "proposal": {"explanation": "Synthetic"}},
    }
    from tests.support import seal

    artifact = validate_bundle(seal(raw))
    experiment = LocalExperiment(
        identity_digest="f" * 64,
        rows=[{"item_id": "test-run", "scores": {"supported": 1}}],
        evaluator_elapsed_ms=2,
        mode="local_no_upload",
    )
    return build_sync_payload(experiment, [artifact])


def test_sync_preserves_original_trace_time_and_parentage():
    data = payload()
    assert data.runs[0]["start_time"] == "2026-10-27T00:00:00Z"
    assert data.runs[0]["end_time"] == "2026-10-27T00:00:01Z"
    assert any(
        r["parent_run_id"] == data.runs[0]["id"] and r["run_type"] == "llm" for r in data.runs[1:]
    )
    state = MemoryState()
    sink = FakeDestination(data)
    first = sync_experiment(data, sink, state)
    assert first["state"] == "confirmed"
    assert sync_experiment(data, sink, state) == first
    assert sink.uploads == 1


def test_ambiguous_upload_reconciles_before_any_duplicate_write():
    data = payload()
    state = MemoryState()
    sink = FakeDestination(data, ambiguous=True)
    assert sync_experiment(data, sink, state)["state"] == "unknown"
    assert sync_experiment(data, sink, state)["state"] == "confirmed"
    assert sink.uploads == 1


def test_missing_approval_never_uploads():
    data = payload()
    sink = FakeDestination(data)
    sink.approved_payload_digest = None
    result = sync_experiment(data, sink, MemoryState())
    assert result["state"] == "not_configured"
    assert sink.saved is None
