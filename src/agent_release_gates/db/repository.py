import hashlib
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from agent_release_gates.artifacts.store import digest, validate_bundle
from agent_release_gates.contracts.artifacts import ArtifactBundle
from agent_release_gates.contracts.datasets import DatasetManifest
from agent_release_gates.contracts.decisions import Decision, GateInput
from agent_release_gates.contracts.labels import HumanLabel, PacketManifest
from agent_release_gates.contracts.scores import JudgeResult, VersionEvaluation
from agent_release_gates.evaluation.gate import decide_release
from agent_release_gates.evaluation.qualification import StudyFreeze, qualify
from agent_release_gates.review.labels import validate_labels

from .models import (
    DatasetRecord,
    DecisionRecord,
    EvaluationRecord,
    EvaluationRun,
    LabelRevision,
    PacketRecord,
    QualificationRecord,
    QualificationRun,
    RunRecord,
    StudyRecord,
    SyncRecord,
)


def identifier(value):
    return str(uuid5(NAMESPACE_URL, value))


def put(session, model, values):
    session.execute(insert(model).values(**values).on_conflict_do_nothing())
    record = session.get(model, values["id"])
    if record is None or any(getattr(record, key) != value for key, value in values.items()):
        raise ValueError("RECORD_CONFLICT")
    return record


class Repository:
    def __init__(self, session_factory):
        self.sessions = session_factory

    def register_dataset(self, raw: bytes) -> DatasetRecord:
        manifest = DatasetManifest.model_validate_json(raw)
        with self.sessions.begin() as session:
            return put(
                session,
                DatasetRecord,
                {
                    "id": hashlib.sha256(raw).hexdigest(),
                    "payload": manifest.model_dump(mode="json"),
                },
            )

    def put_run(self, bundle: ArtifactBundle) -> RunRecord:
        raw = bundle.model_dump(mode="json")
        validate_bundle(raw)
        with self.sessions.begin() as session:
            dataset = session.get(DatasetRecord, bundle.manifest.dataset_digest)
            if dataset is None:
                raise ValueError("DATASET_NOT_REGISTERED")
            cases = {c["case_id"]: c for c in dataset.payload["cases"]}
            case = cases.get(bundle.manifest.case_id)
            if not case or (case["family_id"], case["split"]) != (
                bundle.manifest.family_id,
                bundle.manifest.split,
            ):
                raise ValueError("CASE_IDENTITY")
            try:
                return put(
                    session,
                    RunRecord,
                    {
                        "id": bundle.manifest.run_id,
                        "digest": digest(raw),
                        "dataset_id": dataset.id,
                        "payload": raw["manifest"],
                        "storage_key": f"{bundle.manifest.run_id}/bundle.json",
                    },
                )
            except ValueError as error:
                raise ValueError("RUN_CONFLICT") from error

    def get_run(self, run_id: str) -> RunRecord:
        with self.sessions() as session:
            value = session.get(RunRecord, run_id)
            if value is None:
                raise KeyError("RUN_NOT_FOUND")
            return value

    def list_runs(self) -> list[RunRecord]:
        with self.sessions() as session:
            return list(session.scalars(select(RunRecord).order_by(RunRecord.id)))

    def register_packet(self, packet: PacketManifest, bindings: dict | None = None) -> PacketRecord:
        with self.sessions.begin() as session:
            return put(
                session,
                PacketRecord,
                {
                    "id": packet.packet_digest,
                    "payload": packet.model_dump(mode="json"),
                    "bindings": bindings or {},
                },
            )

    def get_packet(self, packet_id: str) -> PacketRecord:
        with self.sessions() as session:
            record = session.get(PacketRecord, packet_id)
            if record is None:
                raise KeyError("PACKET_NOT_FOUND")
            return record

    def append_labels(self, labels: list[HumanLabel], packet_digest: str) -> LabelRevision:
        with self.sessions.begin() as session:
            packet = session.get(PacketRecord, packet_digest)
            if packet is None:
                raise KeyError("PACKET_NOT_FOUND")
            raw = [l.model_dump(mode="json") for l in labels]
            validate_labels(raw, PacketManifest.model_validate(packet.payload))
            identity = digest({"packet": packet_digest, "labels": raw})
            return put(
                session,
                LabelRevision,
                {
                    "id": identifier(identity),
                    "digest": identity,
                    "packet_id": packet_digest,
                    "payload": raw,
                },
            )

    def get_labels(self, label_id: str) -> LabelRevision:
        with self.sessions() as session:
            record = session.get(LabelRevision, label_id)
            if record is None:
                raise KeyError("LABEL_REVISION_NOT_FOUND")
            return record

    def _save_evaluation(self, session, result: VersionEvaluation) -> EvaluationRecord:
        raw = result.model_dump(mode="json")
        identity = digest(raw)
        for case in result.cases:
            run = session.get(RunRecord, case.run_id)
            if run is None:
                raise KeyError("RUN_NOT_FOUND")
            if (
                run.digest,
                run.dataset_id,
                run.payload["subject_version"],
                run.payload["mode"],
            ) != (
                case.artifact_digest,
                result.manifest_digest,
                result.subject_version,
                result.mode,
            ):
                raise ValueError("EVALUATION_ARTIFACT_MISMATCH")
        record = put(
            session,
            EvaluationRecord,
            {
                "id": identifier(identity),
                "digest": identity,
                "dataset_id": result.manifest_digest,
                "payload": raw,
            },
        )
        for case in result.cases:
            session.execute(
                insert(EvaluationRun)
                .values(evaluation_id=record.id, run_id=case.run_id)
                .on_conflict_do_nothing()
            )
        return record

    def save_evaluation(self, result: VersionEvaluation) -> EvaluationRecord:
        with self.sessions.begin() as session:
            return self._save_evaluation(session, result)

    def get_evaluation(self, evaluation_id: str) -> EvaluationRecord:
        with self.sessions() as session:
            record = session.get(EvaluationRecord, evaluation_id)
            if record is None:
                raise KeyError("EVALUATION_NOT_FOUND")
            return record

    def save_qualification(
        self, label_revision_id: str, results: list[JudgeResult], manifest: DatasetManifest
    ) -> QualificationRecord:
        with self.sessions.begin() as session:
            revision = session.get(LabelRevision, label_revision_id)
            if revision is None:
                raise KeyError("LABEL_REVISION_NOT_FOUND")
            labels = [HumanLabel.model_validate(r) for r in revision.payload]
            value = qualify(labels, results, manifest)
            raw = value.model_dump(mode="json")
            identity = digest(raw)
            for result in results:
                run = session.get(RunRecord, result.run_id)
                if run is None:
                    raise KeyError("RUN_NOT_FOUND")
                dataset = session.get(DatasetRecord, run.dataset_id)
                if digest(dataset.payload) != digest(manifest.model_dump(mode="json")):
                    raise ValueError("QUALIFICATION_DATASET_MISMATCH")
                if run.payload["mode"] == "scripted" and result.mode != "scripted":
                    raise ValueError("JUDGE_MODE_MISMATCH")
            record = put(
                session,
                QualificationRecord,
                {
                    "id": identity,
                    "label_revision_id": revision.id,
                    "payload": raw,
                    "judgments": [r.model_dump(mode="json") for r in results],
                },
            )
            for run_id in {r.run_id for r in results}:
                session.execute(
                    insert(QualificationRun)
                    .values(qualification_id=identity, run_id=run_id)
                    .on_conflict_do_nothing()
                )
            return record

    def get_qualification(self, qualification_id: str) -> QualificationRecord:
        with self.sessions() as session:
            value = session.get(QualificationRecord, qualification_id)
            if value is None:
                raise KeyError("QUALIFICATION_NOT_FOUND")
            return value

    def save_decision(self, value: Decision, inputs: GateInput) -> DecisionRecord:
        if value != decide_release(inputs):
            raise ValueError("DECISION_INPUT_MISMATCH")
        with self.sessions.begin() as session:
            qualification_id = digest(inputs.qualification.model_dump(mode="json"))
            if session.get(QualificationRecord, qualification_id) is None:
                if inputs.qualification.status != "inconclusive":
                    raise ValueError("QUALIFICATION_NOT_REGISTERED")
                qualification_id = None
            baseline = self._save_evaluation(session, inputs.baseline) if inputs.baseline else None
            candidate = self._save_evaluation(session, inputs.candidate)
            return put(
                session,
                DecisionRecord,
                {
                    "id": identifier(value.input_digest),
                    "input_digest": value.input_digest,
                    "baseline_id": baseline.id if baseline else None,
                    "candidate_id": candidate.id,
                    "qualification_id": qualification_id,
                    "payload": value.model_dump(mode="json"),
                    "inputs": inputs.model_dump(mode="json"),
                },
            )

    def get_decision(self, decision_id: str) -> DecisionRecord:
        with self.sessions() as session:
            record = session.get(DecisionRecord, str(decision_id))
            if record is None:
                raise KeyError("DECISION_NOT_FOUND")
            return record

    def advance_study(
        self,
        study_id: str,
        identity_digest: str,
        holdout=False,
        label_revision_id: str | None = None,
    ) -> StudyRecord:
        with self.sessions.begin() as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:identity))"), {"identity": study_id}
            )
            record = session.get(StudyRecord, study_id)
            state = StudyFreeze(**record.payload) if record else StudyFreeze()
            state.begin_holdout(identity_digest) if holdout else state.revise(identity_digest)
            payload = {"revisions": state.revisions, "frozen": state.frozen}
            if record:
                record.payload = payload
            else:
                record = StudyRecord(id=study_id, payload=payload)
                session.add(record)
            if label_revision_id is not None:
                record.calibration_label_id = label_revision_id
            return record

    def get_study(self, study_id: str) -> StudyRecord:
        with self.sessions() as session:
            value = session.get(StudyRecord, study_id)
            if value is None:
                raise KeyError("STUDY_NOT_FOUND")
            return value

    def sync_state(self, identity: str, action: str, remote_ids=None) -> dict:
        with self.sessions.begin() as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:identity))"), {"identity": identity}
            )
            record = session.get(SyncRecord, identity)
            claimed = record is None
            if record is None:
                record = SyncRecord(id=identity, payload={"state": "reserved", "remote_ids": None})
                session.add(record)
            if action == "confirm":
                record.payload = {"state": "confirmed", "remote_ids": remote_ids}
            elif action == "unknown":
                record.payload = {"state": "unknown", "remote_ids": record.payload["remote_ids"]}
            return {**record.payload, "claimed": claimed}
