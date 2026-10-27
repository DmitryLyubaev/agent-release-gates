import hashlib
import json
from pathlib import Path

from agent_release_gates.artifacts.manifest import load_dataset
from agent_release_gates.artifacts.store import digest, import_bundle, validate_bundle
from agent_release_gates.contracts.datasets import ExpectedCase
from agent_release_gates.contracts.decisions import GateInput
from agent_release_gates.contracts.labels import HumanLabel, PacketManifest, ReviewItem
from agent_release_gates.contracts.scores import (
    CHECKS,
    CaseEvaluation,
    ExactResult,
    QualificationResult,
    VersionEvaluation,
)
from agent_release_gates.evaluation.exact import check_exact
from agent_release_gates.evaluation.gate import decide_release
from agent_release_gates.evaluation.judge import JudgePort, LiveJudgePort, judge_saved_item
from agent_release_gates.review.packet import export_packet


class EvaluationService:
    def __init__(self, repository, artifact_root: Path, judge: JudgePort | LiveJudgePort):
        self.repository = repository
        self.root = Path(artifact_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.judge = judge
        self.dataset_root = Path("datasets")
        self.dataset = load_dataset(self.dataset_root)
        self.dataset_record = repository.register_dataset(
            (self.dataset_root / "manifest.json").read_bytes()
        )
        self.rubric_digest = hashlib.sha256(
            Path("rubrics/explanation-v1.json").read_bytes()
        ).hexdigest()
        self.policy_digest = hashlib.sha256(
            Path("policies/release-v1.json").read_bytes()
        ).hexdigest()
        evaluation = Path(__file__).parent / "evaluation"
        self.evaluator_digest = digest(
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(evaluation.glob("*.py"))
            }
        )

    def import_run(self, raw: dict):
        bundle = validate_bundle(raw)
        if bundle.manifest.dataset_digest != self.dataset_record.id:
            raise ValueError("DATASET_MISMATCH")
        try:
            old = self.repository.get_run(bundle.manifest.run_id)
        except KeyError:
            old = None
        if old and old.digest != digest(bundle.model_dump(mode="json")):
            raise ValueError("RUN_CONFLICT")
        receipt = import_bundle(bundle, self.root)
        record = self.repository.put_run(bundle)
        return {"id": record.id, "digest": receipt.digest, "mode": bundle.manifest.mode}

    def read_run(self, run_id):
        record = self.repository.get_run(run_id)
        path = (self.root / record.storage_key).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError("ARTIFACT_MISSING")
        bundle = validate_bundle(json.loads(path.read_bytes()))
        if digest(bundle.model_dump(mode="json")) != record.digest:
            raise ValueError("ARTIFACT_CONFLICT")
        return bundle

    def _item(self, bundle, item_id=None, definition=None):
        proposal = bundle.documents.get("proposal") or {}
        return ReviewItem(
            item_id=item_id or bundle.manifest.run_id,
            case_id=bundle.manifest.case_id,
            family_id=bundle.manifest.family_id,
            split=bundle.manifest.split,
            run_id=bundle.manifest.run_id,
            source_mode="scripted" if bundle.manifest.usage.state == "not_incurred" else "live",
            evidence={
                "snapshot": bundle.documents.get("evidence"),
                "tool_results": [
                    e["payload"]
                    for e in bundle.documents.get("events", [])
                    if e["kind"] == "tool_result"
                ],
            },
            explanation=proposal.get("explanation", ""),
            next_step=proposal.get("nextStep", ""),
            origin="control" if bundle.manifest.mode == "fault_control" else "natural",
            dangerous=definition.dangerous if definition else False,
            rubric_digest=self.rubric_digest,
        )

    def _exact(self, bundle):
        definition = next(c for c in self.dataset.cases if c.case_id == bundle.manifest.case_id)
        expected = ExpectedCase.model_validate_json(
            (self.dataset_root / definition.gold).read_bytes()
        )
        value = check_exact(bundle, expected)
        fixture = json.loads((self.dataset_root / definition.fixture).read_bytes())
        actual = (bundle.documents.get("evidence") or {}).get("policies")
        if actual is not None and sorted(actual, key=lambda p: (p["id"], p["version"])) != sorted(
            fixture["policies"], key=lambda p: (p["id"], p["version"])
        ):
            value = value.model_copy(update={"checks": {**value.checks, "references": "fail"}})
        return value

    def evaluate(self, run_ids):
        bundles = [self.read_run(r) for r in run_ids]
        if not bundles:
            raise ValueError("RUNS_REQUIRED")
        if len({(b.manifest.subject_version, b.manifest.mode) for b in bundles}) != 1:
            raise ValueError("MIXED_VERSIONS")
        identities = {
            (
                b.manifest.subject_commit,
                b.manifest.source_digest,
                b.manifest.adapter_digest,
                digest(b.manifest.settings),
            )
            for b in bundles
        }
        if len(identities) != 1:
            raise ValueError("MIXED_TARGET_IDENTITIES")
        cases = []
        for bundle in bundles:
            item = self._item(bundle)
            judges = [judge_saved_item(item, self.judge, r) for r in [1, 2]]
            cases.append(
                CaseEvaluation(
                    case_id=bundle.manifest.case_id,
                    run_id=bundle.manifest.run_id,
                    artifact_digest=digest(bundle.model_dump(mode="json")),
                    exact=self._exact(bundle),
                    judges=judges,
                )
            )
        version = VersionEvaluation(
            subject_version=bundles[0].manifest.subject_version,
            mode=bundles[0].manifest.mode,
            manifest_digest=self.dataset_record.id,
            evaluator_digest=self.evaluator_digest,
            policy_digest=self.policy_digest,
            usage_complete=all(b.manifest.usage.state != "unknown" for b in bundles)
            and all(j.usage.state != "unknown" for c in cases for j in c.judges),
            cases=cases,
        )
        record = self.repository.save_evaluation(version)
        return {"id": record.id, "evaluation": record.payload}

    def langsmith_local(self, run_ids):
        from agent_release_gates.langsmith.local import evaluate_local

        def nonempty_explanation(outputs):
            return {"key": "nonempty_explanation", "score": bool(outputs.get("explanation"))}

        return evaluate_local(
            [self._item(self.read_run(r)) for r in run_ids], nonempty_explanation
        ).model_dump(mode="json")

    def review_packet(self, run_ids, split, output=None):
        definitions = [d for d in self.dataset.review_items if d.split == split]
        bundles = [self.read_run(r) for r in run_ids]
        items = []
        for definition in definitions:
            matches = [
                b
                for b in bundles
                if b.manifest.case_id == definition.case_id
                and b.manifest.fault_recipe == definition.mutation
            ]
            if len(matches) != 1:
                raise ValueError("REVIEW_ITEM_SOURCE_MISSING_OR_DUPLICATED")
            item = self._item(matches[0], definition.item_id, definition)
            if not item.explanation:
                raise ValueError("NO_EXPLANATION_CAPTURED")
            items.append(item)
        if len(items) != (8 if split == "calibration" else 16):
            raise ValueError("REVIEW_SPLIT_SIZE")
        packet_key = digest({"runs": sorted(run_ids), "split": split, "rubric": self.rubric_digest})
        destination = Path(output) if output else self.root / "reviews" / split / packet_key
        packet = export_packet(items, split, destination)
        bindings = {item.item_id: {"run_id": item.run_id} for item in items}
        self.repository.register_packet(packet, bindings)
        return {
            "packet_id": packet.packet_digest,
            "packet": packet.model_dump(mode="json"),
            "directory": str(destination),
        }

    def import_labels(self, packet_id, rows):
        labels = [HumanLabel.model_validate(r) for r in rows]
        record = self.repository.append_labels(labels, packet_id)
        return {"id": record.id, "packet_id": record.packet_id}

    def qualify(self, packet_id, label_revision_id, study_id):
        record = self.repository.get_packet(packet_id)
        packet = PacketManifest.model_validate(record.payload)
        labels = self.repository.get_labels(label_revision_id)
        if labels.packet_id != packet_id:
            raise ValueError("LABEL_PACKET_MISMATCH")
        definitions = {d.item_id: d for d in self.dataset.review_items}
        items = []
        for item_id, binding in record.bindings.items():
            item = self._item(self.read_run(binding["run_id"]), item_id, definitions[item_id])
            if digest(item.visible()) != packet.item_digests[item_id]:
                raise ValueError("ITEM_TEXT_CHANGED")
            items.append(item)
        if len(items) != len(packet.item_digests):
            raise ValueError("PACKET_BINDINGS_MISSING")
        identity = digest(
            {
                "dataset": self.dataset_record.id,
                "rubric": self.rubric_digest,
                "judge": self.judge.settings_digest,
            }
        )
        if packet.split == "calibration":
            self.repository.advance_study(study_id, identity, label_revision_id=label_revision_id)
        else:
            study = self.repository.get_study(study_id)
            if study.calibration_label_id is None:
                raise ValueError("CALIBRATION_REQUIRED")
            self.repository.advance_study(study_id, identity, holdout=True)
        results = [judge_saved_item(item, self.judge, r) for item in items for r in [1, 2]]
        if packet.split == "calibration":
            return {
                "study_id": study_id,
                "mode": self.judge.mode,
                "judgments": [r.model_dump(mode="json") for r in results],
            }
        qualification = self.repository.save_qualification(label_revision_id, results, self.dataset)
        return {"id": qualification.id, "qualification": qualification.payload}

    def compare(self, baseline_id, candidate_id, qualification_id=None):
        def load(evaluation_id):
            record = self.repository.get_evaluation(evaluation_id)
            value = VersionEvaluation.model_validate(record.payload)
            cases = []
            for case in value.cases:
                try:
                    exact = self._exact(self.read_run(case.run_id))
                except (ValueError, KeyError):
                    exact = ExactResult(checks={c: "missing" for c in CHECKS})
                cases.append(case.model_copy(update={"exact": exact}))
            return value.model_copy(update={"cases": cases})

        baseline = load(baseline_id) if baseline_id else None
        candidate = load(candidate_id)

        def target(version):
            if version is None or not version.cases:
                return {}
            manifest = self.repository.get_run(version.cases[0].run_id).payload
            return {
                key: manifest[key]
                for key in ["subject_commit", "source_digest", "adapter_digest", "settings"]
            }

        targets = {
            key: value
            for key, value in {"baseline": target(baseline), "candidate": target(candidate)}.items()
            if value
        }
        qualification = (
            QualificationResult.model_validate(
                self.repository.get_qualification(qualification_id).payload
            )
            if qualification_id
            else QualificationResult(
                status="inconclusive",
                study_mode="scripted",
                rubric_digest=self.rubric_digest,
                settings_digest=self.judge.settings_digest,
                label_digest="0" * 64,
                evidence_digest="0" * 64,
                metrics=[],
            )
        )
        inputs = GateInput(
            expected_case_ids=[c.case_id for c in self.dataset.cases if c.split == "release"],
            baseline=baseline,
            candidate=candidate,
            qualification=qualification,
            manifest_digest=self.dataset_record.id,
            evaluator_digest=self.evaluator_digest,
            policy_digest=self.policy_digest,
            target_identities=targets,
        )
        decision = decide_release(inputs)
        record = self.repository.save_decision(decision, inputs)
        return self.decision(record.id)

    def decision(self, decision_id):
        record = self.repository.get_decision(decision_id)
        from agent_release_gates.evaluation.report import report_metrics

        manifests = {
            c["run_id"]: self.repository.get_run(c["run_id"]).payload
            for key in ["baseline", "candidate"]
            if record.inputs[key]
            for c in record.inputs[key]["cases"]
        }
        return {
            "id": record.id,
            "decision": record.payload,
            "inputs": record.inputs,
            "metrics": report_metrics(record.inputs, manifests),
        }
