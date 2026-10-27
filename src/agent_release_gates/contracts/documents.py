"""Validate consumed observations without normalizing retained evidence bytes."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StrictStr,
    StringConstraints,
    field_validator,
)

from .artifacts import Difference, Digest, Identifier, Money, TraceEvent, utc

Nonempty = Annotated[StrictStr, StringConstraints(min_length=1)]
Version = Annotated[int, Field(strict=True, gt=0)]


class OpenObservation(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)


class Line(OpenObservation):
    id: Identifier
    netMinor: Money


class Source(OpenObservation):
    id: Identifier
    version: Version
    batchId: Identifier
    receiptId: Identifier
    source: Literal["pos", "accounting"]
    currency: Literal["AUD"]
    basis: Literal["exclusive"]
    rateBps: Literal[1000]
    subtotalMinor: Money
    taxMinor: Money
    grossMinor: Money
    lines: list[Line] | None
    notes: StrictStr | None = None


class Policy(OpenObservation):
    id: Identifier
    version: Version
    batchId: Identifier
    receiptIds: list[Identifier]
    source: Literal["pos", "accounting"]
    rateBps: Literal[1000]
    rounding: Literal["per_item", "per_receipt"]
    text: StrictStr


class Snapshot(OpenObservation):
    batchId: Identifier
    receiptId: Identifier
    digest: Digest
    sources: list[Source]
    policies: list[Policy]


class Reference(OpenObservation):
    kind: Literal["source", "policy"]
    id: Identifier
    version: Version


class Proposal(OpenObservation):
    id: Identifier
    version: Version
    snapshotDigest: Digest
    category: Literal[
        "explained_rounding",
        "insufficient_evidence",
        "contradictory_evidence",
        "unexplained_mismatch",
    ]
    differenceMinor: Difference | None
    evidenceRefs: list[Reference]
    calculationIds: list[StrictStr]
    explanation: Nonempty
    nextStep: Nonempty
    modelVersion: Nonempty
    promptVersion: Nonempty


class Capture(OpenObservation):
    complete: StrictBool
    status: Nonempty
    error: StrictStr | None


class ProviderReceipt(OpenObservation):
    reservation_id: Nonempty
    request: dict
    response: JsonValue | None
    request_id: Nonempty | None
    error: Nonempty | None
    started_at: datetime
    ended_at: datetime
    _utc = field_validator("started_at", "ended_at", mode="before")(utc)


class ConsumedDocuments(OpenObservation):
    evidence: Snapshot | None
    final_sources: list[Source]
    proposal: Proposal | None
    events: list[TraceEvent]
    capture: Capture
    raw_proposals: list[JsonValue] = Field(default_factory=list)
    provider_receipts: list[ProviderReceipt] = Field(default_factory=list)


class ModelRequest(OpenObservation):
    turn: Annotated[int, Field(strict=True, ge=0, le=5)]
    messages: list[dict]


class ModelResponse(OpenObservation):
    turn: Annotated[int, Field(strict=True, ge=0, le=5)]
    reply: dict


class ModelError(OpenObservation):
    turn: Annotated[int, Field(strict=True, ge=0, le=5)]
    code: Nonempty


class ProposalSaved(OpenObservation):
    proposalId: Identifier
    version: Version
    snapshotDigest: Digest


class ReviewRequest(OpenObservation):
    proposalId: Identifier
    proposalVersion: Version
    snapshotDigest: Digest
    idempotencyKey: Identifier
    decision: Literal["accept", "reject", "acknowledge"]


class ReviewRefused(ReviewRequest):
    code: Nonempty


class Outcome(OpenObservation):
    proposalId: Identifier
    snapshotDigest: Digest
    outcome: Literal["reviewed_explained", "open_unresolved"]
    invalidated: StrictBool


class ToolObservation(OpenObservation):
    callId: Identifier
    name: Nonempty
    args: dict
    snapshotDigest: Digest
    result: dict


class CaptureFinished(OpenObservation):
    complete: StrictBool
    status: Nonempty


class RejectedProposal(OpenObservation):
    code: Nonempty


EVENT_PAYLOADS = {
    "model_request": ModelRequest,
    "model_response": ModelResponse,
    "model_error": ModelError,
    "proposal_saved": ProposalSaved,
    "proposal_rejected": RejectedProposal,
    "review_request": ReviewRequest,
    "review_replayed": ReviewRequest,
    "review_refused": ReviewRefused,
    "outcome": Outcome,
    "tool_result": ToolObservation,
    "tool_error": ToolObservation,
    "capture_finished": CaptureFinished,
}


def validate_event_payload(event: TraceEvent):
    payload = EVENT_PAYLOADS[event.kind].model_validate(event.payload)
    if event.kind == "model_request" and any(
        m.get("role") not in ["system", "user", "assistant", "tool"] for m in payload.messages
    ):
        raise ValueError("MESSAGE_ROLE_REQUIRED")
