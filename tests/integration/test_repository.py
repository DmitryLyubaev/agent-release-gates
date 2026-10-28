from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from agent_release_gates.artifacts.store import validate_bundle
from agent_release_gates.evaluation.gate import decide_release
from tests.db_support import registered_bundle, seeded_decision
from tests.support import seal


def test_migration_and_run_reimport_conflict_are_atomic(repo, database):
    artifact, first = registered_bundle(repo)
    assert repo.put_run(artifact).id == first.id
    raw = artifact.model_dump(mode="json")
    raw["documents"]["proposal"]["explanation"] = "Changed"
    with pytest.raises(ValueError, match="RUN_CONFLICT"):
        repo.put_run(validate_bundle(seal(raw)))
    assert len(repo.list_runs()) == 1
    with database[0].begin() as c:
        assert (
            c.execute(text("select version_num from alembic_version")).scalar()
            == "0002_live_studies"
        )


def test_upgrading_existing_offline_schema_preserves_audit_records(repo, database):
    from agent_release_gates.db.session import migrate

    artifact, saved = registered_bundle(repo)
    # This fixture owns a disposable schema. Simulate the previous release's schema.
    with database[0].begin() as connection:
        connection.execute(text("DROP TABLE live_studies"))
        connection.execute(text("UPDATE alembic_version SET version_num='0001_audit'"))
    migrate(database[0])
    assert repo.get_run(saved.id).digest == saved.digest
    assert repo.get_run(saved.id).payload == artifact.manifest.model_dump(mode="json")
    with database[0].begin() as connection:
        assert (
            connection.execute(text("SELECT to_regclass('live_studies')")).scalar()
            == "live_studies"
        )


def test_foreign_keys_refuse_unregistered_dataset(repo):
    from tests.support import bundle

    with pytest.raises((ValueError, IntegrityError)):
        repo.put_run(validate_bundle(bundle()))


def test_concurrent_reimport_returns_one_record(repo):
    artifact, first = registered_bundle(repo)
    with ThreadPoolExecutor(max_workers=4) as workers:
        records = list(workers.map(lambda _: repo.put_run(artifact), range(8)))
    assert {r.id for r in records} == {first.id}


def test_decision_records_reference_inputs_and_cannot_be_updated(repo, database):
    inputs, _ = seeded_decision(repo)
    value = decide_release(inputs)
    saved = repo.save_decision(value, inputs)
    assert saved.payload["status"] == "accept"
    assert repo.save_decision(value, inputs).id == saved.id
    with pytest.raises(DBAPIError), database[0].begin() as c:
        c.execute(text("UPDATE decisions SET payload='{}'::jsonb WHERE id=:id"), {"id": saved.id})


def test_label_correction_does_not_rewrite_old_decision(repo):
    inputs, revision = seeded_decision(repo)
    original = repo.save_decision(decide_release(inputs), inputs)
    from agent_release_gates.contracts.labels import HumanLabel

    rows = deepcopy(revision.payload)
    rows[0]["note"] = "Rechecked the same evidence."
    updated = repo.append_labels([HumanLabel.model_validate(r) for r in rows], revision.packet_id)
    assert updated.id != revision.id
    assert repo.get_decision(original.id).payload == original.payload
    assert repo.get_decision(original.id).qualification_id == original.qualification_id


def test_frozen_study_survives_repository_restart(repo, database):
    from agent_release_gates.db.repository import Repository

    repo.advance_study("study_1", "a" * 64)
    repo.advance_study("study_1", "b" * 64)
    repo.advance_study("study_1", "b" * 64, holdout=True)
    restarted = Repository(database[1])
    with pytest.raises(ValueError, match="FROZEN"):
        restarted.advance_study("study_1", "c" * 64)
