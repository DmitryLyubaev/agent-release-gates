import contextlib
import io
from collections.abc import Callable
from time import perf_counter
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from langsmith import Client, tracing_context
from langsmith.evaluation import evaluate
from langsmith.schemas import Example

from agent_release_gates.artifacts.store import digest
from agent_release_gates.contracts.artifacts import Digest, StrictModel
from agent_release_gates.contracts.labels import ReviewItem


class LocalExperiment(StrictModel):
    identity_digest: Digest
    rows: list[dict]
    evaluator_elapsed_ms: float
    mode: Literal["local_no_upload"]


def evaluate_local(items: list[ReviewItem], evaluator: Callable) -> LocalExperiment:
    if not items or len({i.item_id for i in items}) != len(items):
        raise ValueError("UNIQUE_ITEMS_REQUIRED")
    client = Client(
        api_url="http://127.0.0.1:9",
        api_key="offline-not-a-credential",
        auto_batch_tracing=False,
        info={},
        tracing_mode="langsmith",
        omit_traced_runtime_info=True,
    )
    dataset_id = uuid5(NAMESPACE_URL, "agent-release-gates/local")
    examples = [
        Example(
            id=uuid5(dataset_id, i.item_id), dataset_id=dataset_id, inputs=i.visible(), outputs={}
        )
        for i in items
    ]
    by_id = {i.item_id: i for i in items}

    def target(inputs):
        return {"explanation": inputs["explanation"], "next_step": inputs["next_step"]}

    start = perf_counter()
    try:
        with (
            tracing_context(enabled=False, client=client),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = evaluate(
                target,
                data=examples,
                evaluators=[evaluator],
                client=client,
                upload_results=False,
                disable_evaluator_tracing=True,
                max_concurrency=0,
                blocking=True,
            )
            rows = []
            for row in result:
                item = by_id[row["example"].inputs["item_id"]]
                rows.append(
                    {
                        "item_id": item.item_id,
                        "run_id": item.run_id,
                        "item_digest": digest(item.visible()),
                        "outputs": row["run"].outputs,
                        "scores": {s.key: s.score for s in row["evaluation_results"]["results"]},
                        "error": row["run"].error,
                    }
                )
    finally:
        client.close()
    return LocalExperiment(
        identity_digest=digest({"items": [i.model_dump(mode="json") for i in items], "rows": rows}),
        rows=rows,
        evaluator_elapsed_ms=(perf_counter() - start) * 1000,
        mode="local_no_upload",
    )
