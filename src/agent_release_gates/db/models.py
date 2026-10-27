from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DatasetRecord(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB)


class RunRecord(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    digest: Mapped[str] = mapped_column(String, unique=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    payload: Mapped[dict] = mapped_column(JSONB)
    storage_key: Mapped[str] = mapped_column(String)


class PacketRecord(Base):
    __tablename__ = "packets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB)


class LabelRevision(Base):
    __tablename__ = "label_revisions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    digest: Mapped[str] = mapped_column(String, unique=True)
    packet_id: Mapped[str] = mapped_column(ForeignKey("packets.id"))
    payload: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationRecord(Base):
    __tablename__ = "evaluations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    digest: Mapped[str] = mapped_column(String, unique=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    payload: Mapped[dict] = mapped_column(JSONB)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)


class QualificationRecord(Base):
    __tablename__ = "qualifications"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    label_revision_id: Mapped[str] = mapped_column(ForeignKey("label_revisions.id"))
    payload: Mapped[dict] = mapped_column(JSONB)
    judgments: Mapped[list] = mapped_column(JSONB)


class QualificationRun(Base):
    __tablename__ = "qualification_runs"
    qualification_id: Mapped[str] = mapped_column(ForeignKey("qualifications.id"), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)


class DecisionRecord(Base):
    __tablename__ = "decisions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    input_digest: Mapped[str] = mapped_column(String, unique=True)
    baseline_id: Mapped[str | None] = mapped_column(ForeignKey("evaluations.id"), nullable=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id"))
    qualification_id: Mapped[str] = mapped_column(ForeignKey("qualifications.id"))
    payload: Mapped[dict] = mapped_column(JSONB)
    inputs: Mapped[dict] = mapped_column(JSONB)


class StudyRecord(Base):
    __tablename__ = "study_freezes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB)


class SyncRecord(Base):
    __tablename__ = "sync_states"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB)
