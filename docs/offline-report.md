# Offline evidence

Measured 27 October 2026. This is a bounded synthetic demonstration. The subject workflow executes real reconciliation, tools, SQLite persistence and review transitions; all model replies, judge verdicts and test labels in this report are authored scripts. No actual human labels or paid calls have occurred.

## Observed results

The current cohort contains 20 natural scripted workflow captures and 20 explicit control derivatives, captured afresh after the review fixes. Twelve source families yield eight calibration and sixteen held-out review items; four separate release families compare baseline/candidate prompts. The candidate prompt adds a focused instruction to distinguish observed facts from possible causes and give an evidence-bound next step.

The process demonstration observed the intended CLI results:

| Condition | Result | Exit |
| --- | --- | --- |
| Complete qualifying scripted candidate | accept | 0 |
| Explicit source-money mutation | reject | 1 |
| Unsupported causal prose with exact fields intact | reject | 1 |
| Candidate with one missing release case | inconclusive | 2 |

The scripted judge matches the authored scripted labels on both fixed held-out repetitions. These verdicts deliberately encode the exercise and provide no estimate of model accuracy or independent human agreement. Their purpose is to demonstrate the mechanics and precedence of the gate. A tie between the scripted baseline and candidate is not an improvement claim.

## Verification

- The pre-review Python suite passed 75 tests with PostgreSQL 16.15, including fresh Alembic migration, concurrent import, label revisions, immutable decisions and new-process CLI readback. No integration tests were skipped. Any review-fix verification is recorded separately below.
- Eight Node adapter tests passed against the pinned subject, preserving raw rejected proposals, exercising no-review/repeated/stale transitions, verifying changed prompt identity and refusing compiled-output drift.
- Actual LangSmith Python SDK 0.14.13 local evaluation passed with network calls prohibited and ambient tracing enabled. Hosted synchronization tests used a fake destination; no hosted operation is claimed. The SDK emits known upstream beta/deprecation warnings for local evaluation/key extraction.
- The local Docker image built from locked dependencies and pinned Python/uv images. A fresh Compose project migrated an empty PostgreSQL database, ran the API as UID 10001, imported/read back an artifact in a fresh correctly owned volume, and retained readback after a real API-container restart.
- A separate Linux Node 24 build produced the same normalized compiled JS/SQL fingerprint as the Windows build. No global runtime or Windows feature was changed.
- The GitHub Actions workflow is authored. Hosted CI has not run because the product repository has not been published.

The first broad suite run was interrupted by a simultaneous database-container recreation. The stable rerun passed. Initial container import also exposed a volume-ownership issue; the image now pre-creates the artifact directory for its non-root user, and fresh-volume import/readback passed. A Windows Python SSL-context initialization problem affected the original generic HTTP smoke client; the loopback-only check now uses plain HTTPConnection without changing any TLS verification setting. Live-provider readiness still needs to be tested in its chosen execution environment.

## Provenance and limits

The original cohort and its known request-snapshot defect are preserved under `examples/historical-scripted-v1`, with original adapter bytes retained at `371106b`. Current `examples/scripted` bundles were captured anew with immutable request frames and compiled-output fingerprints. Manifests retain actual adapter/source/settings/dataset digests and capture times. The subject is pinned to `774e4df2d1d05342623ef2b10c42ec69238877f5`; its original checkout, prior reports, fixtures and budget remain unchanged.

## Independent review and fixes

One fresh reviewer identified seven Important issues and no Critical or Minor issues. Each issue was reproduced before its correction: missing baseline evidence, inconsistent/unrelated review events, lifecycle failures hidden by truncation, mutable request frames, incomplete/uncompared target identity, malformed nested documents, and unverified hosted write confirmation. The single consolidated fix pass passed 95 Python tests and nine Node tests, with no skips. No second review or live-model/hosted call was performed.

New regressions exercise the actual API/service and SDK boundary, including SDK sampling at zero and queued writes. A release now requires baseline evidence, matched review commands and complete declared target identities; invalid nested content is refused before persistence. Sync remains unresolved until expected remote records are reconciled. The corrected scripted process demonstration retains all four expected statuses and CLI exit codes.

Hashes bind local inputs; they are not independent authenticity certificates. Exact checks cover the selected synthetic contract rather than universal financial correctness. Tool timestamps without a recorded start are instantaneous observations, not measured tool durations. Derived controls retain their parent capture provenance and are excluded from new-inference cost totals.

Remaining work is actual human calibration/held-out labelling, an approved fresh agent/judge study with a separate budget, a real hosted LangSmith comparison/trace inspection, and separately approved publication. Offline success does not complete those milestones or establish production operation.
