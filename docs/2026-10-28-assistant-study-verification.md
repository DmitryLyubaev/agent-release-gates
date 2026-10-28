# Assistant-reference mode verification, 28 October 2026

The explicit assistant-review mode was implemented and reviewed at `7509c3311bf8d680bdecb194989fd89ef1cee1da`, from base `2b85d664640c655414e6ea0c4f61b04eacb47998`. This is a bounded portfolio demonstration. Actual human validation is unmeasured.

## Verification

- Task 1: 193 Python tests passed, 14 upstream SDK warnings; 19 Node tests passed.
- Task 2: 21 focused tests passed; full 200 Python tests passed in 295.12 seconds, 14 upstream SDK warnings.
- Serial Node suite: 19/19 passed in 39.64 seconds.
- Ruff lint/format: passed, 85 Python files formatted. Git integrity and diff checks passed.
- Meaningful RED/GREEN regressions covered provenance, wrong-policy refusal, persistent transition, CLI dispatch, export/readback metadata and dangerous supported explanations with unsafe actions.
- One fresh read-only whole-branch review on gpt-6-astra high found no Critical, Important or Minor findings. No fix pass or re-review was needed.

At this checkpoint no new provider calls were made. The original allowance retained USD0.126128 spent and zero unsettled charges. The failed first bundle remained SHA256 `42e9aa767f4cb713d326d462f1e7f932052d3f4e3c7e588c4fe3b890470aa780`.

The source is ready for the separately recorded owner-approved automated-only stages under the same cumulative USD10 cap. This verification is not a claim that those stages, hosted acceptance or human validation have occurred. No new public push or hosted transfer is authorized by this record.

## Rulings I made

- Ruling: reuse the dedicated checkout on codex/assistant-review-study because native worktree attachment previously rejected this source root; the ledger/approval paths bind this checkout. Cost: concurrent edits would share the checkout.
- Ruling: keep the original study ID and config digest; add an explicit audited one-way review-mode transition before labels/freeze. This preserves calibration evidence, failure history, exposure and costs without creating another allowance. Cost: mode selection is a state transition, not a second independent study.
- Ruling: initial judge instructions only, with no default tuning/sweep. Cost: a failed qualification remains a measured failure and may prevent release comparison.
- Ruling: count every declared-dangerous combined reference rejection, including supported facts with an unsafe next step, in both modes. The old support-only predicate allowed a dangerous false accept to pass. Cost: dangerous-negative counts become stricter for that case; this enforces the existing zero-false-accept policy rather than relaxing human review.
- Ruling: newly generated assistant-mode packet templates carry assistant provenance; the existing original calibration human template is retained unchanged. Cost: operators must use the separately projected assistant rows for that saved packet.
- Final: Ruling: actual provider outcomes, receipts, costs and hosted acceptance were excluded by the reviewer. Verify actual outcomes and accounting during the approved execution; keep hosted transfer unperformed. Cost: code review alone does not establish real provider or hosted success.
- Final: Ruling: concurrent long-lived LiveStudy instances may retain a previous service policy. Keep the approved command-per-stage CLI workflow, which reconstructs the service from saved mode, rather than extend this bounded demo for concurrent operators. Cost: unsupported long-lived concurrent use can fail closed with a policy mismatch.
- Final: Ruling: previously frozen studies cannot resume across source changes because implementation identity deliberately rejects drift. The approved study is pre-freeze, so retain this behavior and freeze only after integration. Cost: old frozen studies require their original source rather than transparent migration.

## Deferred minors

None.
