import socket
from types import SimpleNamespace

import pytest
from langsmith import Client
from langsmith.utils import LangSmithNotFoundError

from agent_release_gates.langsmith.sync import SdkLangSmithSink, sync_experiment
from tests.unit.test_langsmith_sync import MemoryState, payload


@pytest.mark.parametrize("failure", ["status", "disconnect"])
@pytest.mark.parametrize("writer", ["dataset", "run", "feedback"])
def test_configured_sdk_never_retries_an_ambiguous_write(monkeypatch, failure, writer):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import langsmith

    writes = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            writes.append(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if failure == "disconnect":
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
            else:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b'{"detail":"synthetic local failure"}')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Only metadata/timeout are supplied here. The SDK, HTTP adapter and write are real.
    class MetadataClient(Client):
        def __init__(self, **kw):
            super().__init__(**kw, info={}, timeout_ms=200)

    monkeypatch.setattr(langsmith, "Client", MetadataClient)
    data, state = payload(), MemoryState()
    sink = SdkLangSmithSink.configured(
        api_url=f"http://127.0.0.1:{server.server_port}",
        api_key="local-test-only",
        workspace_id="00000000-0000-0000-0000-000000000001",
        approved_payload_digest=data.identity_digest,
    )
    monkeypatch.setattr(sink, "reconcile", lambda data: None)

    def upload(data):
        if writer == "dataset":
            sink.client.create_dataset("synthetic-test")
        elif writer == "run":
            sink.client.create_run(**data.runs[0], project_name=data.experiment_name)
        else:
            sink.client.create_feedback(run_id=data.runs[0]["id"], key="synthetic", score=0)

    monkeypatch.setattr(sink, "upload", upload)
    try:
        assert sync_experiment(data, sink, state)["state"] == "unknown"
        assert len(writes) == 1
        assert sync_experiment(data, sink, state)["state"] == "unknown"
        assert len(writes) == 1
    finally:
        sink.client.close()
        server.shutdown()
        server.server_close()
        thread.join()


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

        def read_project(self, **kwargs):
            return SimpleNamespace(id="project", reference_dataset_id="dataset")

        def read_example(self, example_id):
            return SimpleNamespace(
                inputs=next(e["inputs"] for e in data.examples if e["id"] == example_id),
                dataset_id="dataset",
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
            self.remote.update({r["id"]: {**r, "session_id": "project"} for r in self.queue})
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
