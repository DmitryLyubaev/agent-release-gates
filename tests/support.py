import hashlib
import json
from copy import deepcopy


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def seal(raw):
    raw = deepcopy(raw)
    raw["manifest"]["documents"] = {k: digest(v) for k, v in raw["documents"].items()}
    return raw


def bundle(run_id="test-run", mode="scripted"):
    return seal(
        {
            "manifest": {
                "schema_version": 1,
                "run_id": run_id,
                "case_id": "r01",
                "family_id": "r01",
                "split": "release",
                "subject_version": "baseline",
                "mode": mode,
                "subject_commit": "a" * 40,
                "source_digest": "b" * 64,
                "adapter_digest": "c" * 64,
                "dataset_digest": "d" * 64,
                "settings": {"model": "scripted-v1", "prompt": "baseline", "tools": "v1"},
                "started_at": "2026-10-27T00:00:00Z",
                "ended_at": "2026-10-27T00:00:01Z",
                "usage": {
                    "state": "not_incurred",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_nano_usd": 0,
                    "reserved_nano_usd": 0,
                    "price_id": None,
                },
                "documents": {},
                "parent_digest": None,
                "fault_recipe": None,
            },
            "documents": {
                "evidence": {
                    "sources": [
                        {"id": "pos", "version": 1, "grossMinor": "2212"},
                        {"id": "accounting", "version": 1, "grossMinor": "2211"},
                    ],
                    "policies": [],
                },
                "final_sources": [
                    {"id": "pos", "version": 1, "grossMinor": "2212"},
                    {"id": "accounting", "version": 1, "grossMinor": "2211"},
                ],
                "proposal": {
                    "id": "p1",
                    "version": 1,
                    "snapshotDigest": "e" * 64,
                    "category": "explained_rounding",
                    "differenceMinor": "1",
                    "evidenceRefs": [
                        {"kind": "source", "id": "pos", "version": 1},
                        {"kind": "source", "id": "accounting", "version": 1},
                    ],
                    "explanation": "Recorded totals differ by one cent.",
                    "nextStep": "Review the cited calculation.",
                },
                "events": [
                    {
                        "seq": 1,
                        "at": "2026-10-27T00:00:00Z",
                        "kind": "proposal_saved",
                        "payload": {"proposalId": "p1"},
                    },
                    {
                        "seq": 2,
                        "at": "2026-10-27T00:00:00Z",
                        "kind": "review_request",
                        "payload": {
                            "proposalId": "p1",
                            "snapshotDigest": "e" * 64,
                            "decision": "accept",
                        },
                    },
                    {
                        "seq": 3,
                        "at": "2026-10-27T00:00:01Z",
                        "kind": "outcome",
                        "payload": {"proposalId": "p1", "outcome": "reviewed_explained"},
                    },
                ],
                "capture": {"complete": True, "status": "completed", "error": None},
            },
        }
    )


def expected():
    return {
        "case_id": "r01",
        "family_id": "r01",
        "split": "release",
        "category": "explained_rounding",
        "difference_minor": "1",
        "source_values": bundle()["documents"]["evidence"]["sources"],
        "required_refs": bundle()["documents"]["proposal"]["evidenceRefs"],
        "review_sequence": "accept_repeat",
        "outcome": "reviewed_explained",
    }
