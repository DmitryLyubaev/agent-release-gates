from copy import deepcopy
from types import SimpleNamespace

import pytest

from agent_release_gates.artifacts.store import digest
from agent_release_gates.langsmith.sync import SdkLangSmithSink, sync_experiment
from tests.unit.test_langsmith_sync import FakeDestination, MemoryState, payload


def hosted_approval(preview, workspace="00000000-0000-0000-0000-000000000001"):
    destination = {
        "api_url": "https://api.smith.langchain.com",
        "workspace_id": workspace,
        "region": "US",
        "retention_days": 14,
        "tier": "test-only",
        "allowance_nano_usd": 0,
        "max_root_traces": 8,
        "personal_account_confirmed": True,
        "retention_confirmed": True,
        "billing_confirmed": True,
    }
    return {
        "approved": True,
        "approved_by": "test-only-reviewer",
        "approved_at": "2026-10-28T00:00:00Z",
        "payload_digest": preview["payload_digest"],
        "destination": destination,
        "destination_digest": digest(destination),
    }


class States:
    def __init__(self):
        self.states = {}

    def reserve(self, key):
        return self.states.setdefault(key, MemoryState()).reserve(key)

    def confirm(self, key, ids):
        self.states[key].confirm(key, ids)

    def mark_unknown(self, key):
        self.states[key].mark_unknown(key)


def preview_fixture():
    package = {
        "schema_version": 1,
        "study_id": "test-only",
        "freeze_digest": "b" * 64,
        "versions": {"baseline": payload().model_dump(mode="json")},
    }
    return {"payload": package, "payload_digest": digest(package)}


@pytest.mark.parametrize(
    "sensitive",
    [{"api_key": "do-not-send"}, {"workspace_id": "private"}, {"text": "sk-ant-" + "a" * 40}],
)
def test_sensitive_fields_cannot_enter_a_preview_or_approved_transfer(sensitive):
    from agent_release_gates.live.hosted import assert_public_safe

    with pytest.raises(ValueError, match="SENSITIVE"):
        assert_public_safe({"evidence": sensitive})


def test_approval_binds_complete_payload_and_destination_before_any_sdk_use():
    from agent_release_gates.live.hosted import sync_approved_preview

    preview = preview_fixture()
    approval = hosted_approval(preview)
    changed = deepcopy(preview)
    changed["payload"]["versions"]["baseline"]["runs"][0]["outputs"]["capture"]["status"] = (
        "altered"
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("MUST_NOT_CONSTRUCT_SINK")

    with pytest.raises(ValueError, match="APPROVAL"):
        sync_approved_preview(changed, approval, States(), sink_factory=forbidden)
    changed_approval = deepcopy(approval)
    changed_approval["destination"]["workspace_id"] = "00000000-0000-0000-0000-000000000002"
    with pytest.raises(ValueError, match="APPROVAL"):
        sync_approved_preview(preview, changed_approval, States(), sink_factory=forbidden)


def test_sync_state_is_bound_to_destination_as_well_as_payload():
    from agent_release_gates.live.hosted import sync_approved_preview

    preview = preview_fixture()
    states = States()
    sinks = []

    def factory(data, destination):
        sink = FakeDestination(data)
        sinks.append(sink)
        return sink

    first = sync_approved_preview(preview, hosted_approval(preview), states, sink_factory=factory)
    assert first["baseline"]["state"] == "confirmed"
    sync_approved_preview(
        preview,
        hosted_approval(preview, workspace="00000000-0000-0000-0000-000000000002"),
        states,
        sink_factory=factory,
    )
    assert [sink.uploads for sink in sinks] == [1, 1]


def test_delayed_visibility_after_ambiguous_upload_does_not_repeat_a_write():
    data = payload()
    state = MemoryState()

    class Delayed(FakeDestination):
        def upload(self, value):
            self.uploads += 1
            raise TimeoutError("May be queued")

    sink = Delayed(data)
    assert sync_experiment(data, sink, state)["state"] == "unknown"
    assert sync_experiment(data, sink, state)["state"] == "unknown"
    assert sink.uploads == 1


def test_reconciliation_does_not_confirm_existing_ids_with_wrong_evidence():
    data = payload()

    class Destination:
        def list_datasets(self, **kwargs):
            return [SimpleNamespace(id="dataset")]

        def read_project(self, **kwargs):
            return SimpleNamespace(id="project", reference_dataset_id="dataset")

        def read_example(self, identity):
            return SimpleNamespace(
                inputs=next(e["inputs"] for e in data.examples if e["id"] == identity),
                dataset_id="dataset",
            )

        def read_run(self, identity):
            expected = next(run for run in data.runs if run["id"] == identity)
            return SimpleNamespace(
                **{**expected, "outputs": {"wrong": "different evidence"}, "session_id": "project"}
            )

        def read_feedback(self, identity):
            return SimpleNamespace(**next(row for row in data.feedback if row["id"] == identity))

    assert SdkLangSmithSink(Destination(), data.identity_digest).reconcile(data) is None


def test_unverified_hosted_billing_cannot_construct_a_client():
    from agent_release_gates.live.hosted import sync_approved_preview

    preview = preview_fixture()
    approval = hosted_approval(preview)
    approval["destination"]["billing_confirmed"] = False
    approval["destination_digest"] = digest(approval["destination"])

    def forbidden(*args, **kwargs):
        raise AssertionError("BILLING_NOT_CONFIRMED")

    with pytest.raises(ValueError, match="APPROVAL"):
        sync_approved_preview(preview, approval, States(), sink_factory=forbidden)
