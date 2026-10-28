"""Offline saved-score projection and an exact-payload hosted transfer gate."""

import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from agent_release_gates.artifacts.store import digest
from agent_release_gates.contracts.artifacts import utc
from agent_release_gates.contracts.scores import VersionEvaluation
from agent_release_gates.evaluation.judge import ScriptedJudge
from agent_release_gates.langsmith.local import LocalExperiment
from agent_release_gates.langsmith.sync import (
    SdkLangSmithSink,
    SyncPayload,
    build_sync_payload,
    sync_experiment,
)
from agent_release_gates.service import EvaluationService


def assert_public_safe(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower().replace("-", "_") in {
                "api_key",
                "authorization",
                "headers",
                "account_id",
                "organization_id",
                "workspace_id",
                "user_id",
            }:
                raise ValueError("SENSITIVE_FIELD_IN_PAYLOAD")
            assert_public_safe(item)
    elif isinstance(value, list):
        for item in value:
            assert_public_safe(item)
    elif isinstance(value, str) and re.search(
        r"sk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN .*PRIVATE KEY-----",
        value,
    ):
        raise ValueError("SENSITIVE_VALUE_IN_PAYLOAD")


def prepare_study_preview(repository, artifact_root: Path, study_id: str) -> dict:
    state = repository.get_live_study(study_id).payload
    if state["status"] != "released" or not state["frozen"]:
        raise ValueError("COMPLETE_SAVED_COMPARISON_REQUIRED")
    service = EvaluationService(repository, artifact_root, ScriptedJudge({}))
    versions = {}
    for name in ["baseline", "candidate"]:
        evaluation_id = state["evaluations"][name]
        evaluation = VersionEvaluation.model_validate(
            repository.get_evaluation(evaluation_id).payload
        )
        if evaluation.mode != "live" or not evaluation.usage_complete or len(evaluation.cases) != 4:
            raise ValueError("LIVE_COMPARISON_EVIDENCE_REQUIRED")
        rows, bundles = [], []
        for case in evaluation.cases:
            bundle = service.read_run(case.run_id)
            if digest(bundle.model_dump(mode="json")) != case.artifact_digest:
                raise ValueError("ARTIFACT_CHANGED")
            bundles.append(bundle)
            scores = {"exact_checks_pass": int(case.exact.passed)}
            for judge in case.judges:
                for key, value in {
                    "support": judge.support,
                    "usefulness": judge.usefulness,
                }.items():
                    scores[f"{key}_r{judge.repetition}"] = (
                        int(value == "yes") if value in ["yes", "no"] else None
                    )
                scores[f"judge_accept_r{judge.repetition}"] = (
                    int(judge.accepts) if judge.state == "scored" else None
                )
            rows.append({"item_id": case.run_id, "run_id": case.run_id, "scores": scores})
        experiment = LocalExperiment(
            identity_digest=digest({"evaluation": evaluation_id, "rows": rows}),
            rows=rows,
            evaluator_elapsed_ms=0,
            mode="local_no_upload",
        )
        versions[name] = build_sync_payload(experiment, bundles).model_dump(mode="json")
    payload = {
        "schema_version": 1,
        "study_id": study_id,
        "freeze_digest": digest(state["frozen"]),
        "versions": versions,
    }
    assert_public_safe(payload)
    return {
        "payload": payload,
        "payload_digest": digest(payload),
        "inventory": {
            name: {
                "examples": len(value["examples"]),
                "spans": len(value["runs"]),
                "feedback": len(value["feedback"]),
            }
            for name, value in versions.items()
        },
        "scope": "Saved scores and original capture times; no model execution, SDK evaluation or upload during preview.",
    }


class DestinationState:
    def __init__(self, state, destination_digest):
        self.state = state
        self.destination_digest = destination_digest

    def key(self, identity):
        return digest({"destination": self.destination_digest, "payload_identity": identity})

    def reserve(self, identity):
        return self.state.reserve(self.key(identity))

    def confirm(self, identity, remote_ids):
        return self.state.confirm(self.key(identity), remote_ids)

    def mark_unknown(self, identity):
        return self.state.mark_unknown(self.key(identity))


def _sdk_sink(payload, destination):
    key = os.environ.get("LANGSMITH_API_KEY")
    if not key:
        raise ValueError("HOSTED_KEY_REQUIRED")
    return SdkLangSmithSink.configured(
        api_url=destination["api_url"],
        api_key=key,
        workspace_id=destination["workspace_id"],
        approved_payload_digest=payload.identity_digest,
    )


def sync_approved_preview(preview, approval, state, *, sink_factory=None):
    try:
        payload = preview["payload"]
        destination = approval["destination"]
        assert_public_safe(payload)
        utc(approval["approved_at"])
        url = urlsplit(destination["api_url"])
        UUID(destination["workspace_id"])
        valid = (
            approval["approved"] is True
            and bool(approval["approved_by"].strip())
            and preview["payload_digest"] == digest(payload) == approval["payload_digest"]
            and digest(destination) == approval["destination_digest"]
            and destination["personal_account_confirmed"] is True
            and destination["retention_confirmed"] is True
            and destination["billing_confirmed"] is True
            and bool(destination["region"].strip())
            and bool(destination["tier"].strip())
            and type(destination["retention_days"]) is int
            and destination["retention_days"] > 0
            and type(destination["allowance_nano_usd"]) is int
            and destination["allowance_nano_usd"] >= 0
            and url.scheme == "https"
            and (
                url.hostname == "api.smith.langchain.com"
                or (url.hostname or "").endswith(".api.smith.langchain.com")
            )
            and not url.username
            and not url.password
            and not url.query
            and not url.fragment
            and url.port in [None, 443]
        )
        root_count = sum(
            run["parent_run_id"] is None
            for value in payload["versions"].values()
            for run in value["runs"]
        )
        valid = (
            valid
            and type(destination["max_root_traces"]) is int
            and root_count <= destination["max_root_traces"]
        )
        if not valid:
            raise ValueError
        parsed = {
            name: SyncPayload.model_validate(value) for name, value in payload["versions"].items()
        }
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise ValueError("HOSTED_APPROVAL_REQUIRED_OR_CHANGED") from error
    bound = DestinationState(state, approval["destination_digest"])
    result = {}
    for name, value in parsed.items():
        sink = (sink_factory or _sdk_sink)(value, destination)
        try:
            result[name] = sync_experiment(value, sink, bound)
        finally:
            if isinstance(sink, SdkLangSmithSink):
                close = getattr(sink.client, "close", None)
                if close:
                    close()
    return result
