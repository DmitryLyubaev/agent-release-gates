from typing import Literal

from .artifacts import Digest, Identifier, StrictModel
from .scores import QualificationResult, VersionEvaluation


class GateInput(StrictModel):
    expected_case_ids: list[Identifier]
    baseline: VersionEvaluation | None
    candidate: VersionEvaluation
    qualification: QualificationResult
    manifest_digest: Digest
    evaluator_digest: Digest
    policy_digest: Digest


class Decision(StrictModel):
    status: Literal["accept", "reject", "inconclusive"]
    reason_codes: list[str]
    input_digest: Digest
    evidence_digests: list[Digest]
