# Agent release gates

A small Python service that evaluates saved synthetic agent runs and records why a version is accepted, rejected or inconclusive. It demonstrates exact checks, a human-review workflow, judge calibration, PostgreSQL audit records and LangSmith integration.

The current milestone is **offline**. The reconciliation workflow is real; model replies, judge verdicts and test labels are authored scripts. They intentionally encode the fixture exercises. No real-model accuracy, actual human agreement, hosted LangSmith operation or production adoption is established.

The current corrected cohort is in `examples/scripted`. The first cohort is retained in `examples/historical-scripted-v1` with its known request-observation defect documented; it is not used by the current demonstration.

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
node --test adapters/project13/tests/capture.test.mjs
uv run pytest -q
docker compose down
```

Tests require real PostgreSQL and refuse destructive setup against a database whose name does not end in `_test`. They create and remove dedicated random schemas, not application tables. Stop containers between sessions; named volumes preserve local evidence. Do not remove volumes if that evidence is still needed.

See [architecture](docs/architecture.md), [evaluation method](docs/evaluation.md), [offline evidence](docs/offline-report.md), and [live readiness](docs/live-readiness.md). The later milestone needs actual human labels, a new approved model allowance and an explicitly configured hosted LangSmith destination. The completed subject's historical fixtures, reports and budget remain unchanged.
