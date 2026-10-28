from agent_release_gates.evaluation.report import report_metrics


def test_report_counts_each_underlying_agent_and_judge_receipt_once():
    usage = {
        "state": "known",
        "input_tokens": 100,
        "output_tokens": 10,
        "cost_nano_usd": 300000,
        "reserved_nano_usd": 0,
        "price_id": "test-price",
    }
    start = "2026-10-28T00:00:00+00:00"
    end = "2026-10-28T00:00:01+00:00"
    judge = {
        "receipt_digest": "d" * 64,
        "usage": usage,
        "started_at": start,
        "ended_at": end,
        "repetition": 1,
    }
    case = {"run_id": "same-run", "case_id": "r01", "exact": {"checks": {}}, "judges": [judge]}
    manifest = {
        "family_id": "r01",
        "mode": "live",
        "started_at": start,
        "ended_at": end,
        "usage": {**usage, "cost_nano_usd": 12000},
    }
    result = report_metrics(
        {"baseline": {"cases": [case]}, "candidate": {"cases": [case]}, "qualification": {}},
        {"same-run": manifest},
    )
    assert result["known_agent_cost_nano_usd"] == 12000
    assert result["known_judge_cost_nano_usd"] == 300000
    assert result["known_total_cost_nano_usd"] == 312000
