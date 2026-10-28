# Live-boundary implementation verification, 28 October 2026

The five-task live implementation is built locally on `codex/live-acceptance`, based on public `main` at `e723a6e`. This is a bounded portfolio demonstration. Actual study provider calls, genuine human labels and hosted LangSmith transfers are all zero. Implementation approval does not activate the proposed USD10 allowance.

The added operator workflow shares one persistent allowance across subject capture and judging, preserves unknown charges, stops at human checkpoints and freezes implementation/settings/evidence identities. The normal API and Docker service remain offline. Hosted preview uses stored evaluator scores and requires separate destination/payload approval before a client can write.

## Independent review and regression evidence

One fresh read-only whole-branch review of `e723a6e..1896ded` found five Important issues, no Critical findings and no Minor findings. All five entered one consolidated fix pass. No second review was requested.

| Finding | Observed failure before fix | Regression after fix |
| --- | --- | --- |
| Parser omitted from frozen identity | Parser-only source change kept the same judge settings digest | Production Python source plus dependency lock bind evaluator/judge identities and cached receipts; parser drift invalidates freeze before held-out capture |
| SDK writes retried below the sync guard | Real installed SDK sent four POSTs to a local failing HTTP server | Both HTTP-adapter and SDK-loop retries disabled; actual dataset, run and feedback writes send once on 503/disconnect, then reconcile only |
| Judge failure skipped exact contracts | Only one of four cases was retained; no known release rejection was saved | Exact checks run across every supplied artifact before judging; incomplete release persists exact-control rejection and honest missing judge coverage |
| HTTP error prose leaked identifiers | Account/org IDs survived in JSON and HTML error bodies | Allowlisted error type, status, byte count and raw-body SHA256 replace unsafe diagnostics in exports and durable journals |
| New study ID reset held-out freshness | A second study reused the same exposed families | Claims persist family IDs/fixture hashes before capture; database-wide serialization checks across study IDs, including interrupted/legacy exposure and renamed identical fixtures |

Final source/review-fix commit: `0316c760be40f99be76c1044a5b2447ab079f9b2`. Results are recorded in [verification JSON](results/live-implementation-2026-10-28.json). The old hosted CI result applies only to public `e723a6e`; this local branch has not run hosted CI.

| Local check | Observed result |
| --- | --- |
| Full Python suite with real PostgreSQL/disposable schemas | 166 passed, 14 non-failing SDK warnings, 440.61 seconds |
| Serial Node suite | 18 passed, 44.48 seconds |
| Ruff lint/format and Git diff whitespace checks | Passed; final whitespace-only formatting followed by parser-identity smoke, 1 passed |
| Scripted process demonstration | accept/reject/reject/inconclusive; CLI exits 0/1/1/2, 24 scripted labels |
| Docker build, API health/import/readback, API restart/readback | Passed; runtime UID 10001 |
| Native/container production implementation fingerprint | Equal: `b6d1b5050b4486f02e3849e2c4f938731de6a6dd89c5e85fd1452cc32d5c6bdf` |
| Selected credential/employer-pattern scan before final documentation commit | Zero matches across 303 historical blobs and 240 working files; all authors personal |
| Git integrity and historical/current captures/reports | `git fsck --full` clean; historical/current evidence unchanged from `e723a6e` |

Owned Compose containers are stopped after verification; named volumes retain evidence. No cloud resource was created.

## Rulings and limits

| Ruling | Consequence or cost |
| --- | --- |
| Native worktree attachment rejected the product source root; use a feature branch in its dedicated checkout | Main stays unchanged, but concurrent writers would share that checkout |
| Predispatch judge refusal stops the paid stage instead of creating a free abstention | Operator correction is required; absent calls never count as judgments |
| Judge revisions retain the original human rubric and packet | New human criteria need a new reviewed study and labels |
| Live operator execution goes through LiveStudy; raw Node CLI stays scripted | No standalone raw live capture command |
| Unknown hosted sync reconciles only | Partial transfer repair needs an explicit operator decision |
| Hosted approval records owner-verified billing/retention settings | It does not configure the vendor account; incorrect verification can affect the invoice |
| Conservatively fingerprint all production Python and the dependency lock | Even unrelated implementation or formatting changes invalidate a frozen live study |
| Actual provider availability, compatibility, dated prices, billing and TLS await external preflight | Local stubbed tests do not prove that a paid call will succeed at the proposed rates |
| Human agreement, explanation quality, live candidate performance and generalization are unmeasured | The eventual judge or candidate can fail; no accuracy claim follows from synthetic tests |
| LangSmith account, region, retention, billing, visibility and transfer await separate approval | Hosted acceptance remains unproven |
| New publication, cloud operations, production deployment and automatic release are outside this implementation authorization | These additions remain local until an integration/publication choice |
| The evidence owner is trusted | Hashes detect drift, not coordinated owner rewriting of evidence, code, approvals and databases |
| Enterprise auth, tenancy, HA, queues, monitoring and scale are excluded | Further work is required for production use |
| Process-crash behavior is tested; power loss, filesystem corruption and disaster recovery are not | Storage failure may need manual recovery |
| Historical fixtures/reports remain byte-preserved without retrospective reassessment | Older reports describe their original implementation |
| A fresh qualification requires fresh held-out family IDs and fixture hashes in the same project database | Reusing an exposed family is blocked; this demo has no regression-reuse qualification mode and does not detect semantic duplicates beyond those identifiers |

Deferred minors: none.

## Next external acceptance

The disabled local proposal is `.local/live/p15-live-20261028/proposal.json`, config digest `d1dd0eb13b248e84c6f1d23d48dd2d4c760e4b669e243205a85cad3ec4cf23f0`. No budget database was created for it. Personal account/key readiness, budget alert, current pricing and explicit calibration allowance approval precede any dispatch. The first approved action is four calibration captures, followed by eight actual human labels. Held-out capture, sixteen labels, qualification/release and hosted approval remain later checkpoints. See [live readiness](live-readiness.md).
