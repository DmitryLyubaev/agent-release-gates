import csv
import html
import io
import json
from pathlib import Path
from typing import Literal

from agent_release_gates.artifacts.store import canonical, digest
from agent_release_gates.contracts.labels import PacketManifest, ReviewItem


def export_packet(
    items: list[ReviewItem],
    split: Literal["calibration", "heldout"],
    output: Path,
    *,
    reference_provenance=None,
) -> PacketManifest:
    if not items or any(i.split != split for i in items):
        raise ValueError("PACKET_SPLIT")
    if len({i.item_id for i in items}) != len(items):
        raise ValueError("DUPLICATE_ITEM")
    if len({i.rubric_digest for i in items}) != 1 or len({i.source_mode for i in items}) != 1:
        raise ValueError("PACKET_IDENTITY")
    if reference_provenance not in [None, "human", "assistant", "scripted"]:
        raise ValueError("REFERENCE_PROVENANCE")
    provenance = reference_provenance or ("human" if items[0].source_mode == "live" else "scripted")
    if items[0].source_mode == "scripted" and provenance != "scripted":
        raise ValueError("REFERENCE_SOURCE_MISMATCH")
    visible = [
        {**i.visible(), "item_digest": digest(i.visible())}
        for i in sorted(items, key=lambda x: digest(x.item_id))
    ]
    item_digests = {i["item_id"]: i["item_digest"] for i in visible}
    manifest = PacketManifest(
        split=split,
        rubric_digest=items[0].rubric_digest,
        item_digests=item_digests,
        packet_digest=digest(
            {
                "visible": visible,
                "runs": [(i.item_id, i.run_id, i.source_mode, i.rubric_digest) for i in items],
            }
        ),
        source_mode=items[0].source_mode,
    )
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    body = [
        '<!doctype html><html><head><meta charset="utf-8"><title>Explanation review</title></head><body><h1>Explanation review</h1><p>For each item: are material claims supported (yes/no/unclear), and is the next step useful (yes/no)? Add a concern note for no/unclear support. Use the JSON template to return your labels.</p>'
    ]
    for value in visible:
        body.append(
            f"<section><h2>{html.escape(value['item_id'])}</h2><pre>{html.escape(json.dumps(value['evidence'], indent=2, ensure_ascii=False))}</pre><p>{html.escape(value['explanation'])}</p><p>{html.escape(value['next_step'])}</p></section>"
        )
    body.append("</body></html>")
    (output / "review.html").write_text("\n".join(body), encoding="utf-8")
    (output / "items.json").write_bytes(canonical(visible))
    (output / "packet.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    template = [
        {
            "item_id": v["item_id"],
            "item_digest": v["item_digest"],
            "support": None,
            "usefulness": None,
            "note": "",
            "reviewer": "",
            "labelled_at": None,
            "rubric_digest": manifest.rubric_digest,
            "provenance": provenance,
        }
        for v in visible
    ]
    (output / "labels-template.json").write_bytes(canonical(template))
    return manifest


def export_csv(items: list[ReviewItem]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["item_id", "explanation", "next_step"])
    for item in items:
        writer.writerow(
            [
                "'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v
                for v in [item.item_id, item.explanation, item.next_step]
            ]
        )
    return output.getvalue()
