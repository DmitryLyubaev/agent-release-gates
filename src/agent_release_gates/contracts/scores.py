from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from .artifacts import Digest, Identifier, StrictModel, Usage, utc

CHECKS = frozenset(
    [
        "case_identity",
        "money",
        "category",
        "references",
        "originals",
        "approval_boundary",
        "outcome",
        "duplicate_review",
        "stale_review",
        "complete",
    ]
)


class ExactResult(StrictModel):
    checks: dict[str, Literal["pass", "fail", "missing"]]

    @property
    def passed(self) -> bool:
        return set(self.checks) == CHECKS and all(v == "pass" for v in self.checks.values())


class JudgeResult(StrictModel):
    item_id: Identifier
    item_digest: Digest
    run_id: Identifier
    rubric_digest: Digest
    settings_digest: Digest
    repetition: Literal[1, 2]
    support: Literal["yes", "no", "unclear"]
    usefulness: Literal["yes", "no", "unknown"]
    reason: str
    evidence_ids: list[str]
    state: Literal["scored", "abstained", "error"]
    mode: Literal["scripted", "live"]
    usage: Usage
    started_at: datetime
    ended_at: datetime
    receipt_digest: Digest | None = Field(default=None, exclude_if=lambda value: value is None)
    _utc = field_validator("started_at", "ended_at", mode="before")(utc)

    @property
    def accepts(self) -> bool:
        return self.state == "scored" and self.support == "yes" and self.usefulness == "yes"


class JudgeAttempt(StrictModel):
    response: dict | None
    usage: Usage
    started_at: datetime
    ended_at: datetime
    receipt_digest: Digest
    error_code: str | None
    _utc = field_validator("started_at", "ended_at", mode="before")(utc)


class QualificationResult(StrictModel):
    status: Literal["pass", "fail", "inconclusive"]
    study_mode: Literal["scripted", "human_live"]
    rubric_digest: Digest
    settings_digest: Digest
    label_digest: Digest
    evidence_digest: Digest
    metrics: list[dict] = Field(default_factory=list)


class CaseEvaluation(StrictModel):
    case_id: Identifier
    run_id: Identifier
    artifact_digest: Digest
    exact: ExactResult
    judges: list[JudgeResult]


class VersionEvaluation(StrictModel):
    subject_version: Identifier
    mode: Literal["scripted", "live", "fault_control"]
    manifest_digest: Digest
    evaluator_digest: Digest
    policy_digest: Digest
    usage_complete: bool
    cases: list[CaseEvaluation]
