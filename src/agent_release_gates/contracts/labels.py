from datetime import datetime
from typing import Literal

from pydantic import field_validator, model_validator

from .artifacts import Digest, Identifier, StrictModel, utc


class ReviewItem(StrictModel):
    item_id: Identifier
    case_id: Identifier
    family_id: Identifier
    split: Literal["calibration", "heldout", "release"]
    run_id: Identifier
    source_mode: Literal["scripted", "live"]
    evidence: dict
    explanation: str
    next_step: str
    origin: Literal["natural", "control"]
    dangerous: bool
    rubric_digest: Digest

    def visible(self) -> dict:
        return {
            key: getattr(self, key) for key in ["item_id", "evidence", "explanation", "next_step"]
        }


class PacketManifest(StrictModel):
    split: Literal["calibration", "heldout"]
    rubric_digest: Digest
    item_digests: dict[Identifier, Digest]
    packet_digest: Digest
    source_mode: Literal["scripted", "live"]


class HumanLabel(StrictModel):
    item_id: Identifier
    item_digest: Digest
    support: Literal["yes", "no", "unclear"]
    usefulness: Literal["yes", "no"]
    note: str
    reviewer: str
    labelled_at: datetime
    rubric_digest: Digest
    provenance: Literal["human", "scripted"]
    _utc = field_validator("labelled_at", mode="before")(utc)

    @model_validator(mode="after")
    def concern(self):
        if not self.reviewer.strip() or (self.support != "yes" and not self.note.strip()):
            raise ValueError("REVIEWER_AND_CONCERN_REQUIRED")
        return self

    @property
    def accepts(self) -> bool:
        return self.support == "yes" and self.usefulness == "yes"
