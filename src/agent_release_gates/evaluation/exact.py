from agent_release_gates.artifacts.store import digest
from agent_release_gates.contracts.artifacts import ArtifactBundle
from agent_release_gates.contracts.datasets import ExpectedCase
from agent_release_gates.contracts.scores import CHECKS, ExactResult

COMMAND_KEYS = ("proposalId", "proposalVersion", "snapshotDigest", "idempotencyKey", "decision")


def check_exact(bundle: ArtifactBundle, expected: ExpectedCase) -> ExactResult:
    docs = bundle.documents
    proposal = docs.get("proposal")
    evidence = docs.get("evidence") or {}
    events = docs["events"]
    complete = bool(
        docs["capture"]["complete"]
        and events
        and events[-1]["kind"] == "capture_finished"
        and events[-1]["payload"]["complete"]
    )
    checks = {key: "missing" for key in CHECKS}

    def put(key, value):
        checks[key] = "pass" if value else "fail"

    put(
        "case_identity",
        (bundle.manifest.case_id, bundle.manifest.family_id, bundle.manifest.split)
        == (expected.case_id, expected.family_id, expected.split),
    )
    checks["complete"] = "pass" if complete else "missing"
    sources = evidence.get("sources")
    if proposal:
        put("category", proposal["category"] == expected.category)
        if proposal["differenceMinor"] != expected.difference_minor:
            checks["money"] = "fail"
    if sources is not None and proposal:
        actual = {(s["id"], s["version"]): s for s in sources}
        gold = {(s["id"], s["version"]): s for s in expected.source_values}
        if any(key not in gold or value != gold[key] for key, value in actual.items()):
            checks["money"] = "fail"
        elif checks["money"] != "fail" and set(actual) == set(gold):
            checks["money"] = "pass"
        refs = proposal["evidenceRefs"]
        keys = lambda values: [(r["kind"], r["id"], r["version"]) for r in values]
        available = {
            (kind, r["id"], r["version"])
            for kind, records in [("source", sources), ("policy", evidence.get("policies", []))]
            for r in records
        }
        declared = keys(refs)
        if len(declared) != len(set(declared)) or set(declared) != set(
            keys(expected.required_refs)
        ):
            checks["references"] = "fail"
        elif set(declared) <= available:
            checks["references"] = "pass"
    if sources is not None:
        finals = docs["final_sources"]
        missing = False
        for source in sources:
            matches = [
                f for f in finals if (f["id"], f["version"]) == (source["id"], source["version"])
            ]
            if len(matches) > 1 or any(digest(f) != digest(source) for f in matches):
                checks["originals"] = "fail"
            if not matches:
                missing = True
        if checks["originals"] != "fail":
            checks["originals"] = (
                "fail" if missing and complete else "missing" if missing else "pass"
            )

    outcomes = [e for e in events if e["kind"] == "outcome"]
    all_requests = [e for e in events if e["kind"] == "review_request"]
    # A later matching review proves an early outcome even if the capture marker
    # or proposal document is absent. Incompleteness cannot erase that observation.
    for outcome in outcomes:
        matching = [
            r
            for r in all_requests
            if r["payload"]["proposalId"] == outcome["payload"]["proposalId"]
            and r["payload"]["snapshotDigest"] == outcome["payload"]["snapshotDigest"]
        ]
        if matching and not any(r["seq"] < outcome["seq"] for r in matching):
            checks["approval_boundary"] = "fail"
    if len(outcomes) > (0 if expected.outcome is None else 1) or any(
        e["payload"]["outcome"] != expected.outcome for e in outcomes
    ):
        checks["outcome"] = "fail"
    elif complete:
        put("outcome", len(outcomes) == (0 if expected.outcome is None else 1))
    if expected.review_sequence != "accept_repeat":
        checks["duplicate_review"] = "pass"
    if expected.review_sequence != "stale":
        checks["stale_review"] = "pass"
    if not proposal:
        return ExactResult(checks=checks)

    def scope(event):
        p = event["payload"]
        return (
            p.get("proposalId") == proposal["id"]
            and p.get("proposalVersion") == proposal["version"]
            and p.get("snapshotDigest") == proposal["snapshotDigest"]
        )

    saved = [
        e
        for e in events
        if e["kind"] == "proposal_saved"
        and e["payload"]["proposalId"] == proposal["id"]
        and e["payload"]["version"] == proposal["version"]
        and e["payload"]["snapshotDigest"] == proposal["snapshotDigest"]
    ]
    requests = [e for e in all_requests if scope(e)]
    command = lambda event: tuple(event["payload"][key] for key in COMMAND_KEYS)

    def prior_save(request):
        return any(e["seq"] < request["seq"] for e in saved)

    def corresponding(event):
        return [r for r in requests if command(r) == command(event)]

    boundary = []
    for outcome in outcomes:
        p = outcome["payload"]
        if p["proposalId"] != proposal["id"] or p["snapshotDigest"] != proposal["snapshotDigest"]:
            boundary.append("fail")
            continue
        prior = [r for r in requests if r["seq"] < outcome["seq"]]
        if not prior:
            boundary.append("fail" if requests else "missing")
            continue
        accepted = []
        for request in prior:
            decision = request["payload"]["decision"]
            allowed = (
                decision == "accept" and proposal["category"] == "explained_rounding"
                if p["outcome"] == "reviewed_explained"
                else decision in ["reject", "acknowledge"] or p.get("invalidated", False)
            )
            refused = any(
                e["kind"] == "review_refused"
                and scope(e)
                and command(e) == command(request)
                and e["seq"] < outcome["seq"]
                for e in events
            )
            accepted.append(allowed and not refused)
        if not any(accepted):
            boundary.append("fail")
        elif not any(prior_save(r) for r in prior):
            boundary.append("fail" if saved else "missing")
        else:
            boundary.append("pass")
    if checks["approval_boundary"] != "fail":
        if "fail" in boundary:
            checks["approval_boundary"] = "fail"
        elif "missing" in boundary:
            checks["approval_boundary"] = "missing"
        elif boundary or (complete and saved):
            checks["approval_boundary"] = "pass"

    if expected.review_sequence == "accept_repeat":
        echoes = [e for e in events if e["kind"] == "review_replayed" and scope(e)]
        valid = [
            e
            for e in echoes
            if any(
                r["seq"] < e["seq"] and prior_save(r) and r["payload"]["decision"] == "accept"
                for r in corresponding(e)
            )
        ]
        contradictory = any(
            any(
                r["payload"]["idempotencyKey"] == e["payload"]["idempotencyKey"]
                and command(r) != command(e)
                for r in requests
            )
            or any(r["seq"] > e["seq"] for r in corresponding(e))
            for e in echoes
        )
        if contradictory:
            checks["duplicate_review"] = "fail"
        elif valid and checks["outcome"] == "pass":
            checks["duplicate_review"] = "pass"
    if expected.review_sequence == "stale":
        refusals = [
            e
            for e in events
            if e["kind"] == "review_refused" and scope(e) and e["payload"]["code"] == "STALE"
        ]
        intended = "accept" if proposal["category"] == "explained_rounding" else "acknowledge"
        valid = [
            e
            for e in refusals
            if any(
                r["seq"] < e["seq"] and prior_save(r) and r["payload"]["decision"] == intended
                for r in corresponding(e)
            )
        ]
        if outcomes:
            checks["stale_review"] = "fail"
        elif valid and complete:
            checks["stale_review"] = "pass"
        elif any(any(r["seq"] > e["seq"] for r in corresponding(e)) for e in refusals):
            checks["stale_review"] = "fail"
    return ExactResult(checks=checks)
