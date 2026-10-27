from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)

Money = Annotated[StrictStr, StringConstraints(pattern=r"^(0|[1-9][0-9]{0,17})$")]
Difference = Annotated[StrictStr, StringConstraints(pattern=r"^(0|-?[1-9][0-9]{0,17})$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,100}$")]
Split = Literal["calibration", "heldout", "release"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def utc(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.utcoffset() != UTC.utcoffset(None):
        raise ValueError("UTC_REQUIRED")
    return value


class Usage(StrictModel):
    state: Literal["not_incurred", "known", "unknown"]
    input_tokens: int = Field(ge=0, strict=True)
    output_tokens: int = Field(ge=0, strict=True)
    cost_nano_usd: int | None = Field(ge=0, strict=True)
    reserved_nano_usd: int = Field(ge=0, strict=True)
    price_id: str | None

    @model_validator(mode="after")
    def account_unknown(self):
        if self.state == "unknown" and (
            self.cost_nano_usd is not None or self.reserved_nano_usd <= 0
        ):
            raise ValueError("UNKNOWN_CHARGE_REQUIRES_RESERVATION")
        if self.state == "known" and (self.cost_nano_usd is None or not self.price_id):
            raise ValueError("KNOWN_CHARGE_REQUIRES_PRICE")
        if self.state == "not_incurred" and any(
            [self.input_tokens, self.output_tokens, self.cost_nano_usd != 0, self.reserved_nano_usd]
        ):
            raise ValueError("SCRIPTED_COST_MUST_BE_ZERO")
        return self


class ArtifactManifest(StrictModel):
    schema_version: Literal[1]
    run_id: Identifier
    case_id: Identifier
    family_id: Identifier
    split: Split
    subject_version: Identifier
    mode: Literal["scripted", "live", "fault_control"]
    subject_commit: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
    source_digest: Digest
    adapter_digest: Digest
    dataset_digest: Digest
    settings: dict[str, str]
    started_at: datetime
    ended_at: datetime
    usage: Usage
    documents: dict[Identifier, Digest]
    parent_digest: Digest | None = None
    fault_recipe: str | None = None

    _utc = field_validator("started_at", "ended_at", mode="before")(utc)

    @field_validator("settings")
    @classmethod
    def required_settings(cls, value):
        import re

        if not {"model", "prompt", "prompt_digest", "tools"} <= set(value):
            raise ValueError("TARGET_SETTINGS_REQUIRED")
        if any(not v.strip() for v in value.values()):
            raise ValueError("EMPTY_TARGET_SETTING")
        for key in ["prompt_digest", "compiled_digest"]:
            if key in value and not re.fullmatch("[a-f0-9]{64}", value[key]):
                raise ValueError("SETTING_DIGEST_REQUIRED")
        return value

    @model_validator(mode="after")
    def coherent(self):
        if self.ended_at < self.started_at:
            raise ValueError("TIME_ORDER")
        if self.mode == "live" and self.usage.state == "not_incurred":
            raise ValueError("LIVE_USAGE_REQUIRED")
        if self.mode == "fault_control" and not (self.parent_digest and self.fault_recipe):
            raise ValueError("FAULT_PROVENANCE_REQUIRED")
        if (
            self.mode == "fault_control"
            and self.settings.get("control_recipe") != self.fault_recipe
        ):
            raise ValueError("CONTROL_SETTING_MISMATCH")
        if self.mode != "fault_control" and "control_recipe" in self.settings:
            raise ValueError("CONTROL_SETTING_ON_NATURAL_RUN")
        return self


class TraceEvent(StrictModel):
    seq: int = Field(ge=1, strict=True)
    at: datetime
    kind: Literal[
        "model_request",
        "model_response",
        "model_error",
        "tool_result",
        "tool_error",
        "proposal_saved",
        "proposal_rejected",
        "review_request",
        "review_replayed",
        "review_refused",
        "outcome",
        "capture_finished",
    ]
    payload: dict[str, Any]

    _utc = field_validator("at", mode="before")(utc)


class ArtifactBundle(StrictModel):
    manifest: ArtifactManifest
    documents: dict[str, Any]

    @model_validator(mode="after")
    def consumed_documents(self):
        from .documents import ConsumedDocuments, validate_event_payload

        documents = ConsumedDocuments.model_validate(self.documents)
        for event in documents.events:
            validate_event_payload(event)
        return self


class ArtifactReceipt(StrictModel):
    run_id: Identifier
    digest: Digest
    storage_key: str
