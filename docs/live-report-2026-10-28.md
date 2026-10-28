# Live judge qualification, 28 October 2026

**Result: qualification failed and release was blocked.** Both held-out repetitions reached 9/16 agreement (56.25%), below the frozen 14/16 requirement. There were zero dangerous false accepts, four false rejections and three abstentions per repetition. Total cumulative provider usage cost was USD0.709166 before tax/FX.

This is a bounded synthetic portfolio experiment, measuring agreement with assistant-generated references. It does not establish human accuracy, independent validation or production safety. The existing [scripted demonstration](offline-report.md) separately exercises accept/reject/inconclusive decisions.

## Method and provenance

The subject was the pinned [payments reconciliation assistant](https://github.com/DmitryLyubaev/payments-reconciliation-assistant/tree/774e4df2d1d05342623ef2b10c42ec69238877f5). Both subject and judge used Anthropic `claude-sonnet-5-5`. Four calibration investigations and four derived controls produced eight reference items. Eight further held-out investigations and eight derived controls produced sixteen items, assessed before held-out judge execution.

All 24 references were labelled by the implementation assistant, with explicit assistant provenance. Actual human labels are zero; the assistant's prior implementation context and visible paired examples limit independence. The default human-qualified policy remains separate and refuses assistant qualification.

The initial judge instructions were used without tuning. Dataset, rubric, source, settings and policy identities were frozen before held-out capture. The fixed qualification rule required 14/16 agreement in each of two repetitions, at least four acceptable and four dangerous-negative references, and zero dangerous false accepts. The held-out reference set contained eight acceptable, eight unacceptable and six declared-dangerous negative items.

## Observed results

| Stage | Sample | Observed result |
| --- | --- | --- |
| Calibration judge | 8 items, 1 repetition | 6/8 agreement; 2 citation abstentions |
| Held-out repetition 1 | 16 items | 9 agreements, 4 false rejections, 3 abstentions, 0 false accepts |
| Held-out repetition 2 | 16 items | 9 agreements, 4 false rejections, 3 abstentions, 0 false accepts |
| Dangerous negatives | 6 per repetition | 0 dangerous false accepts in each |
| Live release comparison | 0 provider calls | Refused: JUDGE_QUALIFICATION_REQUIRED |
| Offline hosted preview | 0 payloads | Refused: COMPLETE_SAVED_COMPARISON_REQUIRED |
| Hosted LangSmith upload | 0 | Unperformed |

Agreement includes abstentions in the denominator. Support agreement was 13/16 and usefulness agreement 7/16 in each repetition. Two of sixteen items changed support/usefulness/state between repetitions. These repetitions and paired controls are correlated, not 32 independent examples.

Four assistant-acceptable items were rejected in both repetitions because the judge required a more explicit statement of amount preservation or the selected human review. The assistant had treated reviewer confirmation, gathering missing evidence or keeping an exception open as useful. These are disagreements with assistant references, not established errors against human ground truth.

Three judgments per held-out repetition included tool-call IDs outside the parser's accepted evidence-ID set and were retained as abstentions. Two calibration judgments had the same citation issue. Original results were not rescored or replaced. No label changes, tuning or favourable reruns followed the failure.

Zero observed dangerous false accepts does not compensate for insufficient agreement. The workflow refused release capture before any release request and refused to construct a hosted payload without a complete comparison. No live baseline/candidate result is claimed.

## Cost and latency

| Stage | Requests | Input tokens | Inclusive output tokens | USD before tax/FX |
| --- | ---: | ---: | ---: | ---: |
| calibration:subject | 16 | 39,709 | 4,671 | 0.126128 |
| calibration:judge | 8 | 24,210 | 2,259 | 0.071010 |
| heldout:subject | 29 | 72,117 | 8,935 | 0.233584 |
| heldout:judge | 32 | 94,502 | 8,944 | 0.278444 |
| Total | 85 | 230,538 | 24,809 | 0.709166 |

The original USD10 cumulative cap was not reset. USD9.290834 remained, with zero unsettled charges. All 85 receipts matched their ledger rows and approved rates: USD2/million input tokens and USD10/million output tokens. Thinking breakdown tokens were included in output totals, not charged twice. This is usage-based accounting, not independent invoice reconciliation.

The total includes the failed first capture: a standard provider-usage metadata change was initially rejected, its usage was reconciled offline after a compatibility fix, and a separately approved recovery retained the failed artifact. There were thirteen subject investigations including that failure, twelve completed. Controls were derived without additional subject inference.

Provider-request latency: n=85, median 3.304 seconds, nearest-rank p95 5.775 seconds, range 1.618-7.241 seconds. Completed subject-investigation latency: n=12, median 18.736 seconds, p95 21.384 seconds, range 14.433-21.384 seconds. The failed investigation is excluded from the completed-investigation summary; its request is included in provider timing. These are distinct from evaluator or whole-stage elapsed time.

## Verification and evidence availability

Implementation evaluated: `0498be714b5ab959c7c1d6ac3312c5dd5b099dd9`, with the same code as reviewed `7509c33`. Local verification passed 200 Python tests, 19 serial Node tests and Ruff; one fresh whole-branch review found no issues. The [verification record](2026-10-28-assistant-study-verification.md) preserves scope decisions. Later publication edits only documentation and the aggregate export.

Offline replay reproduced the failed qualification exactly. Packet digests, frozen identities, all receipts/rates, original failed-artifact immutability and the unchanged blank human template were checked. Owned containers were stopped with evidence volumes retained.

The [machine-readable aggregate](evidence/live-2026-10-28-summary.json) includes qualification metrics, frozen identities, counts, usage and timing. Raw provider messages, references, approval files and the allowance ledger remain private. The public aggregate alone cannot independently reproduce all measurements.

Human-calibrated qualification, a successful live release comparison and actual hosted LangSmith operation remain unproven. The bounded experiment closes at this measured failure; no additional paid runs or recurring work are scheduled.
