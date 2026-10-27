from agent_release_gates.contracts.labels import HumanLabel, PacketManifest


def validate_labels(rows: list[dict], packet: PacketManifest) -> list[HumanLabel]:
    labels = [HumanLabel.model_validate(row) for row in rows]
    if len(labels) != len(packet.item_digests) or {r.item_id for r in labels} != set(
        packet.item_digests
    ):
        raise ValueError("LABEL_SET_MISMATCH")
    for label in labels:
        if (
            label.item_digest != packet.item_digests[label.item_id]
            or label.rubric_digest != packet.rubric_digest
        ):
            raise ValueError("LABEL_IDENTITY_MISMATCH")
        if packet.source_mode == "scripted" and label.provenance != "scripted":
            raise ValueError("SCRIPTED_PACKET_CANNOT_SUPPLY_HUMAN_STUDY")
    return labels
