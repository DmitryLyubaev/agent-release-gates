# Live study: implementation and remaining acceptance

Updated 28 October 2026. Provider requests and hosted transfers below are **not authorized by software/plan approval**. Tests use stubbed HTTPS boundaries and synthetic test labels. The public scripted milestone and its historical reports are preserved.

The [dated implementation record](live-implementation-2026-10-28.md) records the independent review, regression evidence and remaining limits. Frozen identities cover production Python, the dependency lock, subject/adapter sources and request settings. Any implementation change requires renewed qualification. Capture claims retain family IDs and fixture hashes across study IDs in the project database; exposed held-out families cannot qualify again as fresh evidence. The owner remains responsible for avoiding semantically duplicated families with different identifiers and content hashes.

The offline implementation does not authorize paid execution or hosted data transfer. Before the live milestone, choose exact agent/judge provider/model IDs, dated prices, token/attempt limits, a new project-owned USD cap and ledger, and the treatment of uncertain charges. The intended ceilings are 28 subject investigations and 96 judge calls, not a spending estimate. Project 13's historical budget database must remain untouched.

Collect eight actual calibration labels before judge tuning, allow at most two revisions, freeze dataset/rubric/model/settings, then collect sixteen held-out labels without exposing judge results. Run two fixed judge repetitions. Preserve failures and report if qualification or the natural candidate fails; do not rerun until passing or present regression reuse as fresh holdout.

Before LangSmith upload, select the personal account/workspace, region, retention/tier, exact synthetic payload and any allowance. The hosted sink requires the exact approved payload digest and is not instantiated by ordinary CLI/API settings. Original capture intervals remain distinct from SDK replay time. Tool spans lacking a recorded start are labelled instantaneous adapter observations rather than measured tool latency.

Local SDK evaluation is real SDK execution with upload disabled and tracing explicitly disabled, tested against ambient tracing credentials and network prohibition. Hosted synchronization tests use an injected fake destination. They do not establish an actual hosted experiment or successful account/retention configuration. Ambiguous uploads remain unknown and reconcile deterministic remote IDs before any write retry.

Final project completion still requires actual human labels, a real-model baseline/candidate comparison, a passing natural version if it qualifies, a rejected fault control, hosted comparison/trace inspection, honest costs/latencies and separately approved publication of new live evidence. The offline foundation is already public. There is no cloud deployment or production operation in this scope.

## One operator stage per command

Run from the checkout with the pinned subject built and local PostgreSQL running. On this Windows setup Docker is available through `wsl -d Ubuntu -- docker compose -f /mnt/e/Projects/agent-release-gates/compose.yaml up -d --wait db`; native Python/Node execute the study. Use `uv run --native-tls` if the machine needs native certificate trust. TLS verification must remain enabled.

First prepare a private disabled proposal:

```sh
uv run python scripts/live_study.py --config .local/live/p15-live-20261028/proposal.json prepare --study-id p15-live-20261028
```

It proposes `claude-sonnet-5-5`, USD10 cumulative API token usage before tax/FX, at most 28 subject investigations (six messages/eight tools each) and 96 judge attempts. Agent output is capped at 4096 tokens/message; judge output at 1024. The ledger reserves a full-context upper bound before each call, so it may stop before the displayed spend reaches the cap. Unknown usage retains its reservation and halts dispatch. The file is not approved, no ledger is opened, and no key is read. Preparation refuses to overwrite an existing file.

Before enabling it, obtain owner approval for the exact configuration digest and intended stage, verify the personal provider account/key, dated prices and budget alert. Store the personal key only in the process environment as `ANTHROPIC_API_KEY`; never place it in the configuration, command arguments or review packet. Do not use Project 13's budget or paid runner. Allowed stages and the cumulative ledger survive later grant changes; making another output directory does not replenish them.

After that separate approval, run these stages individually with the same config:

```sh
uv run python scripts/live_study.py --config .local/live/p15-live-20261028/proposal.json capture-calibration
```

Stop here. Open the returned `review.html` and supply all eight support/usefulness labels in a copy of `labels-template.json`, including reviewer alias, UTC time and concerns for no/unclear support. The agent does not supply human labels. Then:

```sh
uv run python scripts/live_study.py --config .local/live/p15-live-20261028/proposal.json import-calibration-labels --packet-id PACKET_ID --labels artifacts/calibration-labels.json
uv run python scripts/live_study.py --config .local/live/p15-live-20261028/proposal.json judge-calibration
```

The initial calibration pass has eight judge attempts. If needed, `revise-judge --settings .local/judge-settings.json` accepts one `instructions` string; at most two subsequent revisions are permitted. Each needs another explicit `judge-calibration` command. The human rubric and original packet remain fixed. Optional `calibration-development --round 1` and `--round 2` capture at most eight additional calibration-only candidate runs, only if that stage is authorized. They do not replace the original labelled explanations or supply new agreement ground truth. No held-out case is executed during calibration.

When ready:

```sh
uv run python scripts/live_study.py --config .local/live/p15-live-20261028/proposal.json freeze
uv run python scripts/live_study.py --config .local/live/p15-live-20261028/proposal.json capture-holdout
```

Held-out/release stages also need the corresponding owner-approved stage grants. Freeze binds the dataset, human rubric, judge settings, policy/evaluator, pinned source/compiled code, adapter and baseline/candidate prompts. Stop again for sixteen actual held-out labels, blind to judge scores. Then:

```sh
uv run python scripts/live_study.py --config .local/live/p15-live-20261028/proposal.json qualify-holdout --packet-id PACKET_ID --labels artifacts/heldout-labels.json
uv run python scripts/live_study.py --config .local/live/p15-live-20261028/proposal.json capture-release
uv run python scripts/live_study.py --config .local/live/p15-live-20261028/proposal.json report
```

Qualification runs two fixed repetitions. Failed/inconclusive qualification blocks release execution. A refused budget request does not manufacture an abstention. Failed captures, missing explanations and interrupted stages remain incomplete with their evidence; they cannot be replaced automatically. Repeating a completed command returns its saved result. A pending/interrupted stage needs operator inspection, not a new paid attempt. New study IDs do not restore an untouched holdout claim.

The raw Node capture CLI remains scripted. Live operator work goes through `live_study.py`, which enforces the human checkpoints. The programmatic adapter still captures the actual pinned workflow. Provider request journals are flushed before dispatch, receipts before returning, with credentials/headers excluded. Actual success in the selected live environment still needs to be observed.

## Hosted preview and the separate transfer decision

After a complete saved release comparison, create a local preview without constructing a hosted SDK client:

```sh
uv run python scripts/hosted_preview.py preview --study-id p15-live-20261028 --output .local/live/p15-live-20261028/hosted-preview.json
```

It contains baseline/candidate evidence and their actual saved exact/support/usefulness/acceptance scores. It does not regenerate a verdict or rename the local nonempty-explanation smoke score. The printed inventory counts examples, spans and feedback. Inspect the complete synthetic payload before approving its full digest. Known credential/account fields and token-like values are refused rather than silently transferred.

The private hosted approval must bind `payload_digest`, the complete `destination` and its `destination_digest`, owner alias and UTC approval time. The destination includes `api_url`, personal `workspace_id`, `region`, configured `retention_days`, `tier`, `allowance_nano_usd`, `max_root_traces`, and explicit `personal_account_confirmed`, `retention_confirmed` and `billing_confirmed` flags. These record owner verification of actual workspace settings/quota/billing; the command does not configure account retention or enforce the vendor's invoice. All fields and the hosted allowance remain unset until that separate decision. No key belongs in this file.

Only after approval and with the personal `LANGSMITH_API_KEY` in the environment:

```sh
uv run python scripts/hosted_preview.py sync --approval .local/live/p15-live-20261028/hosted-approval.json --payload .local/live/p15-live-20261028/hosted-preview.json
```

Synchronization state is bound to the destination as well as the payload. Confirmation requires readback of the expected dataset/project/examples, trace evidence and feedback. An ambiguous outcome only reconciles; it does not automatically retry writes if records are missing or not yet visible. Partial repairs need a separate operator decision. Local evidence and decisions remain intact. If the selected runtime cannot initialize verified TLS, stop; do not disable verification.

After observed upload, inspect the comparison and traces in that personal workspace and retain dated run IDs, counts, original versus evaluator timings and costs. Only then claim actual hosted LangSmith experience. Stop local Compose containers between sessions and retain evidence volumes.
