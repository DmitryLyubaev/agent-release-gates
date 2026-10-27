import socket

import requests

from agent_release_gates.langsmith.local import evaluate_local
from tests.unit.test_review import item


def test_actual_sdk_local_evaluation_has_no_network_even_with_ambient_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "ambient-must-not-be-used")
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("network")
        raise RuntimeError("NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(requests.Session, "request", forbidden)

    def has_explanation(outputs):
        return {"key": "has_explanation", "score": bool(outputs["explanation"])}

    result = evaluate_local([item(), item(item_id="item_02")], has_explanation)
    assert len(result.rows) == 2
    assert all(r["scores"]["has_explanation"] == 1 for r in result.rows)
    assert result.mode == "local_no_upload"
    assert result.evaluator_elapsed_ms >= 0
    assert attempts == []
