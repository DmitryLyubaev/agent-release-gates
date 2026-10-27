import json

import pytest

from agent_release_gates.contracts.labels import ReviewItem
from agent_release_gates.review.labels import validate_labels
from agent_release_gates.review.packet import export_csv, export_packet


def item(item_id="item_01", split="calibration", source_mode="scripted"):
    return ReviewItem(
        item_id=item_id,
        case_id="c01",
        family_id="c01",
        split=split,
        run_id="run_1",
        source_mode=source_mode,
        evidence={"notes": "<script>alert(1)</script>"},
        explanation='=HYPERLINK("bad")',
        next_step="Review evidence.",
        origin="control",
        dangerous=True,
        rubric_digest="a" * 64,
    )


def test_blind_packet_escapes_text_and_hides_origin(tmp_path):
    packet = export_packet([item()], "calibration", tmp_path)
    html = (tmp_path / "review.html").read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    raw = json.loads((tmp_path / "items.json").read_bytes())
    assert set(raw[0]) == {"item_id", "evidence", "explanation", "next_step", "item_digest"}
    assert packet.item_digests["item_01"] == raw[0]["item_digest"]
    csv = export_csv([item()])
    assert "'=HYPERLINK" in csv


def test_calibration_packet_cannot_read_heldout(tmp_path):
    with pytest.raises(ValueError, match="SPLIT"):
        export_packet([item(split="heldout")], "calibration", tmp_path)


def test_labels_require_complete_frozen_packet_and_valid_review(tmp_path):
    packet = export_packet([item(source_mode="live")], "calibration", tmp_path)
    row = {
        "item_id": "item_01",
        "item_digest": packet.item_digests["item_01"],
        "support": "no",
        "usefulness": "no",
        "note": "Unsupported causal claim.",
        "reviewer": "reviewer-1",
        "labelled_at": "2026-10-27T00:00:00Z",
        "rubric_digest": "a" * 64,
        "provenance": "human",
    }
    assert validate_labels([row], packet)[0].support == "no"
    for rows in [
        [],
        [row, row],
        [{**row, "item_digest": "b" * 64}],
        [{**row, "note": ""}],
        [{**row, "support": "maybe"}],
    ]:
        with pytest.raises(ValueError):
            validate_labels(rows, packet)
