from datetime import UTC, datetime
from typing import Literal, Protocol

from agent_release_gates.artifacts.store import digest
from agent_release_gates.contracts.artifacts import StrictModel, Usage
from agent_release_gates.contracts.labels import ReviewItem
from agent_release_gates.contracts.scores import JudgeAttempt, JudgeResult


class JudgeResponse(StrictModel):
    support: Literal["yes", "no", "unclear"]
    usefulness: Literal["yes", "no", "unknown"]
    evidence_ids: list[str]
    reason: str


class JudgePort(Protocol):
    mode: str
    settings_digest: str

    def evaluate(self, payload: dict) -> dict: ...


class LiveJudgePort(Protocol):
    mode: str
    settings_digest: str

    def evaluate_attempt(self, payload: dict, *, attempt_key: str) -> JudgeAttempt: ...


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


def judge_saved_item(item: ReviewItem, judge: JudgePort | LiveJudgePort, repetition: int) -> JudgeResult:
    if judge.mode == "live":
        attempt = judge.evaluate_attempt(
            {**item.visible(), "rubric_digest": item.rubric_digest},
            attempt_key="judge:"
            + digest(
                {
                    "item": item.visible(),
                    "run": item.run_id,
                    "settings": judge.settings_digest,
                    "repetition": repetition,
                }
            ),
        )
        response = (
            JudgeResponse.model_validate(attempt.response)
            if attempt.response and not attempt.error_code
            else JudgeResponse(
                support="unclear",
                usefulness="unknown",
                evidence_ids=[],
                reason="JUDGE_UNAVAILABLE_OR_INVALID",
            )
        )
        return JudgeResult(
            item_id=item.item_id,
            item_digest=digest(item.visible()),
            run_id=item.run_id,
            rubric_digest=item.rubric_digest,
            settings_digest=judge.settings_digest,
            repetition=repetition,
            **response.model_dump(),
            state="scored" if attempt.response and not attempt.error_code else "abstained",
            mode="live",
            usage=attempt.usage,
            started_at=attempt.started_at,
            ended_at=attempt.ended_at,
            receipt_digest=attempt.receipt_digest,
        )
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
