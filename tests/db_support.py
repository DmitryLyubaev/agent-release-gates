from pathlib import Path

from agent_release_gates.artifacts.store import validate_bundle
from agent_release_gates.contracts.decisions import GateInput
from agent_release_gates.contracts.labels import PacketManifest
from tests.support import bundle, gate_input, qualification_fixture, seal


def registered_bundle(repo, run_id="run_r01", case_id="r01", version="baseline"):
    dataset = repo.register_dataset(Path("datasets/manifest.json").read_bytes())
    raw = bundle(run_id)
    raw["manifest"].update(
        case_id=case_id,
        family_id=case_id,
        subject_version=version,
        dataset_digest=dataset.id,
        split="heldout" if case_id.startswith("h") else "release",
    )
    artifact = validate_bundle(seal(raw))
    return artifact, repo.put_run(artifact)


def seeded_decision(repo):
    from agent_release_gates.artifacts.manifest import load_dataset

    labels, results, _manifest = qualification_fixture()
    packet = PacketManifest(
        split="heldout",
        rubric_digest="b" * 64,
        item_digests={l.item_id: l.item_digest for l in labels},
        packet_digest="a" * 64,
        source_mode="scripted",
    )
    repo.register_packet(packet)
    revision = repo.append_labels(labels, packet.packet_digest)
    for run_id in {r.run_id for r in results}:
        registered_bundle(repo, run_id, run_id.removeprefix("run_"))
    qualification = repo.save_qualification(revision.id, results, load_dataset("datasets"))
    raw = gate_input()
    raw["qualification"] = qualification.payload
    for key in ["baseline", "candidate"]:
        for case in raw[key]["cases"]:
            run_id = key + "_" + case["case_id"]
            artifact, record = registered_bundle(repo, run_id, case["case_id"], key)
            case["run_id"] = run_id
            case["artifact_digest"] = record.digest
            for judge in case["judges"]:
                judge["run_id"] = run_id
        raw[key]["manifest_digest"] = artifact.manifest.dataset_digest
        raw["target_identities"][key] = {
            k: artifact.manifest.model_dump(mode="json")[k]
            for k in ["subject_commit", "source_digest", "adapter_digest", "settings"]
        }
    raw["manifest_digest"] = raw["candidate"]["manifest_digest"]
    return GateInput.model_validate(raw), revision
