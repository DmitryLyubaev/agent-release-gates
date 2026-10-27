from agent_release_gates.artifacts.store import digest
from agent_release_gates.contracts.decisions import Decision, GateInput


def decide_release(inputs: GateInput) -> Decision:
    candidate = inputs.candidate
    evidence = [c.artifact_digest for c in candidate.cases] + [inputs.qualification.evidence_digest]

    def result(status, *reasons):
        return Decision(
            status=status,
            reason_codes=list(reasons),
            input_digest=digest(inputs.model_dump(mode="json")),
            evidence_digests=evidence,
        )

    if any("fail" in c.exact.checks.values() for c in candidate.cases):
        return result("reject", "EXACT_VIOLATION")
    baseline = inputs.baseline
    expected = set(inputs.expected_case_ids)
    if baseline is None or len(expected) != 4 or len(inputs.expected_case_ids) != 4:
        return result("inconclusive", "BASELINE_OR_CASE_CONTRACT_MISSING")
    for version in [baseline, candidate]:
        if len(version.cases) != 4 or {c.case_id for c in version.cases} != expected:
            return result("inconclusive", "CASE_SET_INCOMPLETE")
        if (version.manifest_digest, version.evaluator_digest, version.policy_digest) != (
            inputs.manifest_digest,
            inputs.evaluator_digest,
            inputs.policy_digest,
        ):
            return result("inconclusive", "INCOMPARABLE_IDENTITIES")
        if not version.usage_complete:
            return result("inconclusive", "USAGE_UNRESOLVED")
    qualification = inputs.qualification
    if qualification.status != "pass":
        return result("inconclusive", "JUDGE_UNQUALIFIED")
    live = baseline.mode == "live" or candidate.mode == "live"
    if (qualification.study_mode == "human_live") != live:
        return result("inconclusive", "STUDY_MODE_MISMATCH")
    for version in [baseline, candidate]:
        for case in version.cases:
            if len(case.judges) != 2 or {j.repetition for j in case.judges} != {1, 2}:
                return result("inconclusive", "JUDGE_REPETITIONS_MISSING")
            for judge in case.judges:
                if (judge.rubric_digest, judge.settings_digest) != (
                    qualification.rubric_digest,
                    qualification.settings_digest,
                ) or judge.run_id != case.run_id:
                    return result("inconclusive", "JUDGE_IDENTITY_MISMATCH")
                if (
                    (judge.mode == "live") != live
                    or judge.state != "scored"
                    or judge.support == "unclear"
                    or judge.usefulness == "unknown"
                    or judge.usage.state == "unknown"
                ):
                    return result("inconclusive", "JUDGE_ABSTAINED_OR_UNSETTLED")
    if any(not j.accepts for c in candidate.cases for j in c.judges):
        return result("reject", "SEMANTIC_VIOLATION")
    if not all(c.exact.passed for c in candidate.cases):
        return result("inconclusive", "EXACT_EVIDENCE_INCOMPLETE")
    count = lambda v: sum(c.exact.passed and all(j.accepts for j in c.judges) for c in v.cases)
    if count(candidate) < count(baseline):
        return result("reject", "BASELINE_DECLINE")
    return result("accept", "ALL_RELEASE_CHECKS_PASSED")
