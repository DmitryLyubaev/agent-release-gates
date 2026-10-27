from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from agent_release_gates.contracts.artifacts import ArtifactBundle, Digest, Identifier, StrictModel


class RunRequest(StrictModel):
    run_ids: list[Identifier] = Field(min_length=1, max_length=32)


class PacketRequest(RunRequest):
    split: Literal["calibration", "heldout"]


class LabelsRequest(StrictModel):
    packet_id: Digest
    rows: list[dict] = Field(min_length=1, max_length=24)


class CompareRequest(StrictModel):
    baseline_id: str | None
    candidate_id: str
    qualification_id: Digest | None = None


class QualifyRequest(StrictModel):
    packet_id: Digest
    label_revision_id: str
    study_id: Identifier


def create_app(service) -> FastAPI:
    app = FastAPI(title="Agent release gates", version="0.1.0")

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        if len(await request.body()) > 4 * 1024 * 1024:
            return JSONResponse({"error": "BODY_TOO_LARGE"}, status_code=413)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def invalid(_request, error):
        return JSONResponse({"error": str(error).splitlines()[0][:160]}, status_code=409)

    @app.exception_handler(KeyError)
    async def missing(_request, _error):
        return JSONResponse({"error": "NOT_FOUND"}, status_code=404)

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": "offline"}

    @app.post("/runs/import")
    def import_run(value: ArtifactBundle):
        return service.import_run(value.model_dump(mode="json"))

    @app.get("/runs")
    def runs():
        return [
            {"id": r.id, "digest": r.digest, "manifest": r.payload}
            for r in service.repository.list_runs()
        ]

    @app.get("/runs/{run_id}")
    def run(run_id: str):
        return service.read_run(run_id).model_dump(mode="json")

    @app.post("/review/packets")
    def packet(value: PacketRequest):
        return service.review_packet(value.run_ids, value.split)

    @app.post("/labels/import")
    def labels(value: LabelsRequest):
        return service.import_labels(value.packet_id, value.rows)

    @app.post("/evaluations")
    def evaluate(value: RunRequest):
        return service.evaluate(value.run_ids)

    @app.post("/qualifications")
    def qualify(value: QualifyRequest):
        return service.qualify(value.packet_id, value.label_revision_id, value.study_id)

    @app.post("/comparisons")
    def compare(value: CompareRequest):
        return service.compare(value.baseline_id, value.candidate_id, value.qualification_id)

    @app.get("/decisions/{decision_id}")
    def decision(decision_id: str):
        return service.decision(decision_id)

    return app
