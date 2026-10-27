from datetime import UTC, datetime
from typing import Literal, Protocol

from agent_release_gates.artifacts.store import digest
from agent_release_gates.contracts.artifacts import StrictModel, Usage
from agent_release_gates.contracts.labels import ReviewItem
from agent_release_gates.contracts.scores import JudgeResult


class JudgeResponse(StrictModel):
    support: Literal["yes", "no", "unclear"]
    usefulness: Literal["yes", "no", "unknown"]
    evidence_ids: list[str]
    reason: str


class JudgePort(Protocol):
    mode: str
    settings_digest: str

    def evaluate(self, payload: dict) -> dict: ...


class ScriptedJudge:
    mode = "scripted"

    def __init__(self, responses: dict):
        self.responses = responses
        serializable = {
            k: {"error": type(v).__name__} if isinstance(v, Exception) else v
            for k, v in responses.items()
        }
        self.settings_digest = digest({"mode": "scripted", "responses": serializable})

    def evaluate(self, payload):
        value = self.responses[payload["item_id"]]
        if isinstance(value, Exception):
            raise value
        return value


def judge_saved_item(item: ReviewItem, judge: JudgePort, repetition: int) -> JudgeResult:
    if judge.mode != "scripted":
        raise ValueError("LIVE_MODE_NOT_CONFIGURED")
    start = datetime.now(UTC)
    state = "scored"
    try:
        response = JudgeResponse.model_validate(
            judge.evaluate({**item.visible(), "rubric_digest": item.rubric_digest})
        )
    except Exception:  # noqa: BLE001 - adapter boundary must sanitize external errors and abstain
        state = "abstained"
        response = JudgeResponse(
            support="unclear",
            usefulness="unknown",
            evidence_ids=[],
            reason="JUDGE_UNAVAILABLE_OR_INVALID",
        )
    return JudgeResult(
        item_id=item.item_id,
        item_digest=digest(item.visible()),
        run_id=item.run_id,
        rubric_digest=item.rubric_digest,
        settings_digest=judge.settings_digest,
        repetition=repetition,
        **response.model_dump(),
        state=state,
        mode="scripted",
        usage=Usage(
            state="not_incurred",
            input_tokens=0,
            output_tokens=0,
            cost_nano_usd=0,
            reserved_nano_usd=0,
            price_id=None,
        ),
        started_at=start,
        ended_at=datetime.now(UTC),
    )
