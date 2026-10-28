# Agent release gates

A small Python service that evaluates saved synthetic agent runs and records why a version is accepted, rejected or inconclusive. It demonstrates exact checks, a human-review workflow, judge calibration, PostgreSQL audit records and LangSmith integration.

Two dated demonstrations are available. The [offline study](docs/offline-report.md) uses scripted model replies, judge verdicts and labels to exercise the release mechanics. The [real-model study, 28 October 2026](docs/live-report-2026-10-28.md) finished with **failed judge qualification and a blocked release**.

| Real-model result | Measured outcome |
| --- | --- |
| Held-out agreement | 9/16 in each repetition; 14/16 required |
| Dangerous false accepts | 0/6 dangerous negatives per repetition |
| Other held-out outcomes | 4 false rejections and 3 abstentions per repetition |
| Cumulative usage | 85 requests, USD0.709166 before tax/FX |
| Reference provenance | 24 assistant-generated labels; zero actual human labels |

The gate retained the failed outcome and refused further release capture. No tuning or favourable rerun followed. These figures measure agreement with assistant references, not human accuracy or independent validation. No live baseline/candidate comparison or hosted LangSmith operation is established. See the [full report](docs/live-report-2026-10-28.md) and [aggregate evidence](docs/evidence/live-2026-10-28-summary.json).

The corrected scripted cohort is in `examples/scripted`. The first cohort remains byte-preserved in `examples/historical-scripted-v1` with its known request-observation defect documented. Historical scripted reports remain unchanged.

Live capture, judging and staged review are implemented. Explicit assistant review has a separately named policy; the default human-qualified policy remains distinct. Paid calls occur only through the approved operator workflow. The ordinary API and Docker service remain offline.

To prepare a new study without contacting a provider:

```sh
uv run python scripts/live_study.py --config .local/live/p15-new-study/proposal.json prepare --study-id p15-new-study
```

This creates a disabled allowance proposal and prints its digest. It neither opens the database nor reads a key. New paid work requires its own explicit scope/account/budget approval; exposed held-out cases do not become fresh evidence under a new study ID. Follow [live readiness](docs/live-readiness.md) for the human or explicitly authorized assistant-reference path.

## Run locally

Requirements: Python 3.12, uv 0.10.7, Node 24, Git and a working Docker engine with Compose.

```sh
uv sync --locked
git clone https://github.com/DmitryLyubaev/payments-reconciliation-assistant .local/subject
git -C .local/subject checkout --detach 774e4df2d1d05342623ef2b10c42ec69238877f5
npm --prefix .local/subject ci
npm --prefix .local/subject run build
docker compose up -d --wait db
```

Run `bash scripts/demo.sh`, or `./scripts/demo.ps1` from PowerShell. The script imports committed, real-workflow captures, exercises eight calibration and sixteen held-out **scripted** labels, then checks these actual CLI exits:

| Demonstration | Expected status | CLI exit |
| --- | --- | --- |
| Qualifying scripted candidate | accept | 0 |
| Changed source amount control | reject | 1 |
| Unsupported explanation control with exact fields intact | reject | 1 |
| Candidate missing one case | inconclusive | 2 |

Reports are retained under `artifacts/`; decisions and their immutable dependencies survive service restart in PostgreSQL. Reimporting identical evidence is idempotent. Repeated demo runs create new scripted experiments, while report/readback of an existing decision does not re-evaluate it.

For the container API:

```sh
docker compose build
docker compose up -d --wait api
uv run python scripts/container_smoke.py
```

The API listens on loopback port 55416; PostgreSQL uses loopback port 55415 with deliberately local-only demonstration credentials. Browse API documentation at `http://127.0.0.1:55416/docs`. Native API startup is `uv run uvicorn agent_release_gates.settings:app_factory --factory --host 127.0.0.1 --port 8000`. The default judge abstains; the scripted demo explicitly supplies its authored judge file. No API route launches a model or a shell command.

The Windows validation used an existing Ubuntu Docker engine through WSL and native Windows Python/Node. On that arrangement, prefix Docker commands with `wsl -d Ubuntu --` and use the Linux form of project paths for Compose. No Docker Desktop installation or Windows feature change is required if that engine is already available.

## Capture and inspect

`node adapters/project13/capture.mjs --mode scripted --split release --output artifacts/fresh` captures new isolated subject runs. It refuses live mode. `node adapters/project13/make-demo.mjs --output artifacts/new-scripted` generates a fresh complete scripted cohort; an existing output directory is refused to protect frozen examples.

`uv run release-gates --help` lists import, review packet, labels, evaluation, qualification, comparison, report and local LangSmith commands. `langsmith-local --run-id <registered-run-id>` uses the actual Python SDK with uploads and tracing disabled. Its nonempty-explanation score is an integration smoke check, not an explanation-quality measurement.

## Verify

```sh
uv run ruff check .
uv run ruff format --check .
node --test --test-concurrency=1 adapters/project13/tests/*.test.mjs
uv run pytest -q
docker compose down
```

Tests require real PostgreSQL and refuse destructive setup against a database whose name does not end in `_test`. They create and remove dedicated random schemas, not application tables. Stop containers between sessions; named volumes preserve local evidence. Do not remove volumes if that evidence is still needed.

See [architecture](docs/architecture.md), [evaluation method](docs/evaluation.md), [offline evidence](docs/offline-report.md), [live results](docs/live-report-2026-10-28.md), and [live readiness](docs/live-readiness.md). Human-calibrated validation and hosted LangSmith operation remain unproven. The completed subject's historical fixtures, reports and budget remain unchanged.
