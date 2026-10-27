import socket
from types import SimpleNamespace

import pytest
from langsmith import Client
from langsmith.utils import LangSmithNotFoundError

from agent_release_gates.langsmith.sync import SdkLangSmithSink, sync_experiment
from tests.unit.test_langsmith_sync import MemoryState, payload


@pytest.mark.parametrize("write_mode", ["sampled_out", "queued"])
def test_sdk_wrapper_confirms_only_reconciled_records(monkeypatch, write_mode):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("network")
        raise RuntimeError("NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    data = payload().model_copy(update={"feedback": []})
    sdk = Client(
        api_url="http://127.0.0.1:9",
        api_key="offline",
        auto_batch_tracing=False,
        tracing_sampling_rate=0,
        info={},
        tracing_mode="langsmith",
    )

    class DestinationClient:
        def __init__(self):
            self.remote = {}
            self.queue = []
            self.sdk_returned = False

        def list_datasets(self, **kwargs):
            return [SimpleNamespace(id="dataset")]

        def create_project(self, *args, **kwargs):
            return SimpleNamespace(id="project")

        def read_example(self, example_id):
            return SimpleNamespace(
                inputs=next(e["inputs"] for e in data.examples if e["id"] == example_id)
            )

        def read_run(self, run_id):
            if run_id not in self.remote:
                raise LangSmithNotFoundError("not yet visible")
            return self.remote[run_id]

        def create_run(self, **run):
            if write_mode == "sampled_out":
                sdk.create_run(**run)
                self.sdk_returned = True
            else:
                self.queue.append(run)

        def flush(self):
            self.remote.update({r["id"]: r for r in self.queue})
            self.queue = []

    destination = DestinationClient()
    sink = SdkLangSmithSink(destination, data.identity_digest)
    try:
        result = sync_experiment(data, sink, MemoryState())
        if write_mode == "sampled_out":
            assert result["state"] == "unknown"
            assert sink.reconcile(data) is None
            assert destination.sdk_returned
        else:
            assert result["state"] == "confirmed"
            assert sink.reconcile(data) is not None
        assert attempts == []
    finally:
        sdk.close()
