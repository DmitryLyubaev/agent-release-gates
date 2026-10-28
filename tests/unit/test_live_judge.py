import json
from pathlib import Path

import pytest

from agent_release_gates.evaluation.judge import judge_saved_item
from tests.live_support import allowance, judge_reply, judge_transport, ledger
from tests.unit.test_review import item


def live_item():
    import hashlib

    value = item(source_mode="live")
    return value.model_copy(
        update={
            "evidence": {"snapshot": {"sources": [{"id": "source_1", "version": 1}]}},
            "rubric_digest": hashlib.sha256(
                Path("rubrics/explanation-v1.json").read_bytes()
            ).hexdigest(),
        }
    )


def live_judge(root, response=None, fail=False):
    from agent_release_gates.live.judge import AnthropicJudge

    approval = allowance(root)
    return AnthropicJudge(
        settings={"stage": "calibration"},
        approval=approval,
        ledger_path=Path(approval["config"]["ledger_path"]),
        artifact_root=root / "artifacts",
        transport=judge_transport(response or judge_reply(), fail),
    )


def test_parser_only_source_change_invalidates_judge_identity_and_cached_attempt(
    tmp_path, monkeypatch
):
    from agent_release_gates.live import judge as implementation

    before = live_judge(tmp_path)
    payload = {**live_item().visible(), "rubric_digest": before.rubric_digest}
    before.evaluate_attempt(payload, attempt_key="parser-change")
    parser = Path(implementation.__file__).resolve()
    read_bytes = Path.read_bytes

    def changed_source(path):
        raw = read_bytes(path)
        return raw + b"\n# simulated parser revision\n" if path.resolve() == parser else raw

    monkeypatch.setattr(Path, "read_bytes", changed_source)
    after = live_judge(tmp_path)
    assert after.settings_digest != before.settings_digest
    with pytest.raises(ValueError, match="CONFLICT"):
        after.evaluate_attempt(payload, attempt_key="parser-change")


def test_actual_judge_worker_records_cost_and_receipt_binding_without_another_send(tmp_path):
    judge = live_judge(
        tmp_path,
        judge_reply(
            usage={
                "input_tokens": 100,
                "output_tokens": 10,
                "speed": "standard",
                "output_tokens_details": {"thinking_tokens": 0},
            }
        ),
    )
    result = judge_saved_item(live_item(), judge, 1)
    assert result.accepts and result.mode == "live"
    assert result.usage.cost_nano_usd == 300_000
    assert result.receipt_digest
    assert judge_saved_item(live_item(), judge, 1) == result
    assert len(ledger(allowance(tmp_path)).summary()["calls"]) == 1
    receipts = list((tmp_path / "artifacts/judge").glob("*.json"))
    assert len(receipts) == 1
    assert "test-judge-secret" not in receipts[0].read_text()


@pytest.mark.parametrize(
    "reply",
    [
        judge_reply(content=[{"type": "text", "text": "not json"}]),
        judge_reply(content=[{"type": "text", "text": '{"support":"yes"}'}]),
        judge_reply(stop_reason="max_tokens"),
        judge_reply(stop_reason="refusal"),
        judge_reply(
            content=[
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "support": "yes",
                            "usefulness": "yes",
                            "evidence_ids": ["invented_999"],
                            "reason": "Fictional support.",
                        }
                    ),
                }
            ]
        ),
    ],
)
def test_malformed_refused_or_invented_support_abstains_but_retains_charge(tmp_path, reply):
    result = judge_saved_item(live_item(), live_judge(tmp_path, reply), 1)
    assert not result.accepts
    assert result.state == "abstained"
    assert result.usage.state == "known"
    assert result.usage.cost_nano_usd == 300_000
    assert result.receipt_digest


def test_ambiguous_judge_call_preserves_reservation_and_cannot_score(tmp_path):
    judge = live_judge(tmp_path, fail=True)
    result = judge_saved_item(live_item(), judge, 1)
    assert result.state == "abstained"
    assert result.usage.state == "unknown"
    assert result.usage.reserved_nano_usd == 2_010_240_000
    assert not result.accepts
    assert "credential-value" not in json.dumps(result.model_dump(mode="json"))
    with pytest.raises(ValueError, match="ATTEMPT_REFUSED|UNSETTLED"):
        judge_saved_item(live_item(), judge, 2)
    assert len(ledger(allowance(tmp_path)).summary()["calls"]) == 1


def test_unknown_judge_spend_prevents_human_live_qualification():
    from agent_release_gates.contracts.artifacts import Usage
    from agent_release_gates.evaluation.qualification import qualify
    from tests.support import qualification_fixture

    labels, results, manifest = qualification_fixture()
    labels = [label.model_copy(update={"provenance": "human"}) for label in labels]
    known = Usage(
        state="known",
        input_tokens=1,
        output_tokens=1,
        cost_nano_usd=12000,
        reserved_nano_usd=0,
        price_id="price-test",
    )
    results = [
        r.model_copy(update={"mode": "live", "usage": known, "receipt_digest": "b" * 64})
        for r in results
    ]
    unknown = Usage(
        state="unknown",
        input_tokens=0,
        output_tokens=0,
        cost_nano_usd=None,
        reserved_nano_usd=2010240000,
        price_id="price-test",
    )
    results[0] = results[0].model_copy(update={"usage": unknown})
    assert qualify(labels, results, manifest).status == "inconclusive"


def test_crashed_worker_leaves_a_predispatch_request_journal(tmp_path):
    import subprocess

    from agent_release_gates.live.judge import AnthropicJudge

    approval = allowance(tmp_path)

    def crash_worker(request):
        program = """
import {judgeMessage} from './adapters/project13/provider.mjs';
let text='';for await(const part of process.stdin)text+=part;
await judgeMessage({...JSON.parse(text),apiKey:'test-crash-key',transport:async()=>process.exit(19)});
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", program],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 19
        return {"ok": False, "error": "WORKER_INTERRUPTED"}

    judge = AnthropicJudge(
        settings={"stage": "calibration"},
        approval=approval,
        ledger_path=Path(approval["config"]["ledger_path"]),
        artifact_root=tmp_path / "artifacts",
        transport=crash_worker,
    )
    result = judge_saved_item(live_item(), judge, 1)
    assert result.usage.state == "unknown"
    journals = list((tmp_path / "artifacts/provider").glob("*.json"))
    assert len(journals) == 1
    journal = json.loads(journals[0].read_bytes())
    assert journal["request"]["model"] == "claude-sonnet-5-5"
    assert journal["response"] is None
    assert "test-crash-key" not in journals[0].read_text()


def test_predispatch_budget_refusal_halts_instead_of_creating_an_abstention(tmp_path):
    from agent_release_gates.live.judge import AnthropicJudge

    approval = allowance(tmp_path, cap_nano_usd=2_010_240_000)
    judge = AnthropicJudge(
        settings={"stage": "calibration"},
        approval=approval,
        ledger_path=Path(approval["config"]["ledger_path"]),
        artifact_root=tmp_path / "artifacts",
        transport=judge_transport(judge_reply()),
    )
    assert judge_saved_item(live_item(), judge, 1).accepts
    with pytest.raises(ValueError, match="ATTEMPT_REFUSED|BUDGET_LIMIT"):
        judge_saved_item(live_item(), judge, 2)
    assert len(ledger(approval).summary()["calls"]) == 1
