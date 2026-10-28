from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from .artifacts import ArtifactManifest, Digest, Identifier, StrictModel
from .scores import QualificationResult, VersionEvaluation


class TargetIdentity(StrictModel):
    subject_commit: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
    source_digest: Digest
    adapter_digest: Digest
    settings: dict[str, str]

    @field_validator("settings")
    @classmethod
    def required(cls, value):
        return ArtifactManifest.required_settings(value)


class GateInput(StrictModel):
    review_mode: Literal["human", "assistant"] = Field(
        default="human", exclude_if=lambda value: value == "human"
    )
    expected_case_ids: list[Identifier]
    baseline: VersionEvaluation | None
    candidate: VersionEvaluation
    qualification: QualificationResult
    manifest_digest: Digest
    evaluator_digest: Digest
    policy_digest: Digest
    comparison_issues: list[str] = Field(default_factory=list)
    target_identities: dict[Literal["baseline", "candidate"], TargetIdentity] = Field(
        default_factory=dict
    )


class Decision(StrictModel):
    status: Literal["accept", "reject", "inconclusive"]
    reason_codes: list[str]
    input_digest: Digest
    evidence_digests: list[Digest]
