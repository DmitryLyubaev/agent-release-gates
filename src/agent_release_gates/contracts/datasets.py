from typing import Any, Literal

from pydantic import model_validator

from .artifacts import Difference, Digest, Identifier, Split, StrictModel


class ExpectedCase(StrictModel):
    case_id: Identifier
    family_id: Identifier
    split: Split
    category: str
    difference_minor: Difference | None
    source_values: list[dict[str, Any]]
    required_refs: list[dict[str, Any]]
    review_sequence: Literal["none", "accept_repeat", "acknowledge", "stale"]
    outcome: str | None


class CaseDefinition(StrictModel):
    case_id: Identifier
    family_id: Identifier
    split: Split
    scenario: str
    fixture: str
    gold: str
    fixture_digest: Digest
    gold_digest: Digest


class ReviewDefinition(StrictModel):
    item_id: Identifier
    case_id: Identifier
    family_id: Identifier
    split: Literal["calibration", "heldout"]
    mutation: str | None
    dangerous: bool


class DatasetManifest(StrictModel):
    schema_version: Literal[1]
    cases: list[CaseDefinition]
    review_items: list[ReviewDefinition]

    @model_validator(mode="after")
    def isolate(self):
        families = {}
        for case in self.cases:
            if case.family_id in families and families[case.family_id] != case.split:
                raise ValueError("FAMILY_SPLIT")
            families[case.family_id] = case.split
        by_case = {c.case_id: c for c in self.cases}
        if len(by_case) != len(self.cases) or len({i.item_id for i in self.review_items}) != len(
            self.review_items
        ):
            raise ValueError("DUPLICATE_ITEM")
        for item in self.review_items:
            case = by_case.get(item.case_id)
            if not case or (item.family_id, item.split) != (case.family_id, case.split):
                raise ValueError("REVIEW_FAMILY_SPLIT")
        return self
