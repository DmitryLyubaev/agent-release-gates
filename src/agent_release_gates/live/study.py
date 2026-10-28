"""Small persistent operator workflow. Every paid stage is a separate command."""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from agent_release_gates.artifacts.store import digest, validate_bundle
from agent_release_gates.contracts.artifacts import utc
from agent_release_gates.contracts.labels import ReviewLabel
from agent_release_gates.evaluation.judge import ScriptedJudge, judge_saved_item
from agent_release_gates.service import EvaluationService

from .budget import BudgetLedger
from .judge import AnthropicJudge


def node_json(program, request):
    result = subprocess.run(
        ["node", "--input-type=module", "-e", program],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=900,
    )
    if result.returncode:
        raise ValueError("SUBJECT_OR_PROVIDER_FAILED")
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise ValueError("SUBJECT_RESPONSE_INVALID") from error


class LiveStudy:
    def __init__(
        self,
        repository,
        artifact_root: Path,
        config: dict,
        *,
        capture_runner=None,
        judge_transport=None,
    ):
        self.repository = repository
        self.root = Path(artifact_root).resolve()
        self.config = config
        self.approval = config["approval"]
        self.ledger = BudgetLedger(Path(self.approval["config"]["ledger_path"]), self.approval)
        self.id = self.approval["config"]["study_id"]
        self.subject_root = str(Path(config.get("subject_root", ".local/subject")).resolve())
        self.service = EvaluationService(repository, self.root, ScriptedJudge({}))
        if self.service.dataset_record.id != self.approval["config"]["dataset_digest"]:
            raise ValueError("APPROVAL_DATASET_MISMATCH")
        self.capture_runner = capture_runner or self._capture
        self.injected_capture = capture_runner is not None
        self.judge_transport = judge_transport
        self.config_digest = digest(
            {
                "allowance": self.approval["config_digest"],
                "subject_root": self.subject_root,
                "artifact_root": str(self.root),
                "dataset": self.service.dataset_record.id,
                "rubric": self.service.rubric_digest,
                "initial_judge": config.get("judge_settings", {}),
            }
        )
        try:
            _ = self.state
        except KeyError:
            self.repository.live_study(
                self.id,
                self.config_digest,
                {
                    "revision": 0,
                    "status": "new",
                    "pending": None,
                    "results": {},
                    "captures": {},
                    "judge_settings": config.get("judge_settings", {}),
                    "judge_revisions": [],
                    "calibration_label_id": None,
                    "heldout_label_id": None,
                    "frozen": None,
                    "used_families": [],
                },
            )
        if self.review_mode == "assistant":
            self.service = EvaluationService(
                repository, self.root, ScriptedJudge({}), review_mode="assistant"
            )

    @property
    def state(self):
        return self.repository.live_study(self.id, self.config_digest)

    @property
    def review_mode(self):
        return self.state.get("review_mode", "human")

    def authorize_assistant_review(self, approval):
        state = self.state
        try:
            utc(approval["approved_at"])
            packet_id = state["results"]["capture_calibration"]["packet_id"]
            if (
                approval.get("approved") is not True
                or not isinstance(approval.get("approved_by"), str)
                or not approval["approved_by"].strip()
                or approval.get("study_id") != self.id
                or approval.get("allowance_config_digest") != self.approval["config_digest"]
                or approval.get("packet_id") != packet_id
                or approval.get("review_mode") != "assistant"
                or approval.get("human_validation") is not False
                or approval.get("budget_reset") is not False
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("REVIEW_MODE_APPROVAL_REQUIRED_OR_CHANGED") from error
        binding = digest(approval)
        if state.get("review_mode") == "assistant":
            if state.get("review_mode_approval", {}).get("digest") != binding:
                raise ValueError("REVIEW_MODE_APPROVAL_CHANGED")
        else:
            if (
                state["status"] != "calibration_review"
                or state["pending"]
                or state["frozen"]
                or state["calibration_label_id"]
                or state["heldout_label_id"]
                or any("heldout" in key for key in state["captures"])
            ):
                raise ValueError("REVIEW_MODE_STAGE_REQUIRED")
            self._write(
                _expected=state,
                review_mode="assistant",
                review_mode_approval={"digest": binding, "approval": approval},
            )
        self.service = EvaluationService(
            self.repository, self.root, ScriptedJudge({}), review_mode="assistant"
        )
        return {
            "review_mode": "assistant",
            "policy_digest": self.service.policy_digest,
            "approval_digest": binding,
        }

    def _write(self, _expected=None, _claim_split=None, **updates):
        before = self.state if _expected is None else _expected

        def families(split):
            return [
                {"family_id": case.family_id, "fixture_digest": case.fixture_digest}
                for case in self.service.dataset.cases
                if case.split == split
            ]

        return self.repository.live_study(
            self.id,
            self.config_digest,
            {**before, **updates, "revision": before["revision"] + 1},
            before["revision"],
            claim_families=families(_claim_split) if _claim_split else None,
            heldout_families=families("heldout")
            if _claim_split in ["calibration", "heldout"]
            else None,
        )

    def _operation(self, key, allowed, next_status, work):
        state = self.state
        if key in state["results"]:
            return state["results"][key]
        if state["pending"] or state["status"] not in allowed:
            raise ValueError("STUDY_STAGE_REQUIRED_OR_INTERRUPTED")
        split = {
            "capture_calibration": "calibration",
            "capture_heldout": "heldout",
            "capture_release": "release",
        }.get(key)
        self._write(_expected=state, _claim_split=split, pending=key)
        try:
            result = work()
        except Exception as error:
            code = (
                str(error) if re.fullmatch(r"[A-Z_]{1,100}", str(error)) else "STUDY_STAGE_FAILED"
            )
            self._write(pending=None, status="incomplete", error=code)
            raise ValueError(code) from error
        self._write(
            pending=None, status=next_status, results={**self.state["results"], key: result}
        )
        return result

    def _require(self, stage, *, capture=False):
        if stage not in self.approval["allowed_stages"]:
            raise ValueError("STAGE_NOT_APPROVED")
        if self.ledger.summary()["unsettled_calls"]:
            raise ValueError("USAGE_UNRESOLVED")
        if (
            (capture and not self.injected_capture)
            or (not capture and self.judge_transport is None)
        ) and not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError("ANTHROPIC_KEY_REQUIRED")

    def _judge(self, stage):
        return AnthropicJudge(
            {**self.state["judge_settings"], "stage": stage},
            self.approval,
            self.ledger.path,
            self.root,
            self.judge_transport,
        )

    def _capture(self, request):
        return node_json(
            """
import {captureCase} from './adapters/project13/capture.mjs';
import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
let text='';for await(const part of process.stdin)text+=part;const r=JSON.parse(text);
const m=await captureCase({subjectRoot:r.subject_root,caseDefinition:r.case,subjectVersion:r.version,outputRoot:r.output,mode:'live',approval:r.approval,ledgerPath:r.ledger,pythonExecutable:r.python,investigationId:r.investigation_id,stage:r.stage});
process.stdout.write(await readFile(join(r.output,m.run_id,'bundle.json')));
""",
            request,
        )

    def _identity(self):
        subject = node_json(
            """
import {loadSubject} from './adapters/project13/subject.mjs';
let text='';for await(const part of process.stdin)text+=part;
const s=await loadSubject(JSON.parse(text).root);
process.stdout.write(JSON.stringify({commit:s.commit,source:s.sourceDigest,compiled:s.compiledDigest,request:s.LIVE_IDENTITY.requestDigest,baseline:s.LIVE_IDENTITY.systemPrompt,candidate:s.LIVE_IDENTITY.systemPrompt+'\\nDistinguish observed facts from possible causes, and give one evidence-bound next step.'}));
""",
            {"root": self.subject_root},
        )
        for key in ["baseline", "candidate"]:
            subject[key] = hashlib.sha256(subject[key].encode()).hexdigest()
        files = [
            "capture.mjs",
            "subject.mjs",
            "observe.mjs",
            "mutate.mjs",
            "live-model.mjs",
            "provider.mjs",
        ]
        adapter = hashlib.sha256(
            "".join(
                hashlib.sha256((Path("adapters/project13") / name).read_bytes()).hexdigest()
                for name in files
            ).encode()
        ).hexdigest()
        return {
            "review_mode": self.review_mode,
            "subject": subject,
            "adapter": adapter,
            "dataset": self.service.dataset_record.id,
            "rubric": self.service.rubric_digest,
            "policy": self.service.policy_digest,
            "evaluator": self.service.evaluator_digest,
            "judge": self._judge("calibration").settings_digest,
            "calibration_label_id": self.state["calibration_label_id"],
        }

    def _verify_freeze(self):
        if not self.state["frozen"] or self._identity() != self.state["frozen"]:
            raise ValueError("STUDY_FROZEN_IDENTITY_CHANGED_OR_MISSING")

    def _natural_batch(self, split, version, stage, key):
        runs = []
        identity = self.state["frozen"] or self._identity()
        for case in self.service.dataset.cases:
            if case.split != split:
                continue
            investigation = f"{self.id}:{key}:{case.case_id}:{version}"
            request = {
                "case": case.model_dump(mode="json"),
                "version": version,
                "stage": stage,
                "investigation_id": investigation,
                "subject_root": self.subject_root,
                "approval": self.approval,
                "ledger": str(self.ledger.path),
                "python": sys.executable,
                "output": str(self.root / "captures" / self.id),
            }
            raw = self.capture_runner(request)
            bundle = validate_bundle(raw)
            if (
                bundle.manifest.case_id,
                bundle.manifest.split,
                bundle.manifest.subject_version,
                bundle.manifest.mode,
            ) != (case.case_id, split, version, "live"):
                raise ValueError("CAPTURE_IDENTITY")
            record = self.service.import_run(raw)
            runs.append(record["id"])
            self._write(captures={**self.state["captures"], key + ":" + version: list(runs)})
            target = identity["subject"]
            manifest = bundle.manifest
            if (
                manifest.subject_commit,
                manifest.source_digest,
                manifest.adapter_digest,
                manifest.settings.get("compiled_digest"),
                manifest.settings.get("model"),
                manifest.settings.get("prompt_digest"),
            ) != (
                target["commit"],
                target["source"],
                identity["adapter"],
                target["compiled"],
                self.approval["config"]["model"],
                target[version],
            ):
                raise ValueError("CAPTURE_IDENTITY")
            if (
                not bundle.documents.get("proposal")
                or not bundle.documents["capture"]["complete"]
                or bundle.documents["capture"]["status"] == "failed"
            ):
                raise ValueError("CAPTURE_INCOMPLETE_OR_NO_EXPLANATION")
            if bundle.manifest.usage.state == "unknown":
                raise ValueError("CAPTURE_USAGE_UNRESOLVED")
        return runs

    def _derive(self, run_id, recipe):
        raw = node_json(
            """
import {mutateBundle} from './adapters/project13/mutate.mjs';
let text='';for await(const part of process.stdin)text+=part;const r=JSON.parse(text);
process.stdout.write(JSON.stringify(mutateBundle(r.bundle,r.recipe)));
""",
            {"bundle": self.service.read_run(run_id).model_dump(mode="json"), "recipe": recipe},
        )
        return self.service.import_run(raw)["id"]

    def _review_capture(self, split):
        runs = self._natural_batch(split, "baseline", split, "capture_" + split)
        by_case = {self.service.read_run(run).manifest.case_id: run for run in runs}
        controls = [
            self._derive(by_case[item.case_id], item.mutation)
            for item in self.service.dataset.review_items
            if item.split == split and item.mutation
        ]
        packet = self.service.review_packet(runs + controls, split)
        return {
            **packet,
            "run_ids": runs + controls,
            "next_action": "label_eight_calibration_items"
            if split == "calibration"
            else "label_sixteen_heldout_items",
        }

    def capture_calibration(self):
        if "capture_calibration" in self.state["results"]:
            return self.state["results"]["capture_calibration"]
        self._require("calibration", capture=True)
        return self._operation(
            "capture_calibration",
            ["new"],
            "calibration_review",
            lambda: self._review_capture("calibration"),
        )

    def _labels(self, packet_id, file, split):
        expected = self.state["results"]["capture_" + split]["packet_id"]
        if packet_id != expected:
            raise ValueError("LABEL_PACKET_MISMATCH")
        rows = json.loads(Path(file).read_bytes())
        labels = [ReviewLabel.model_validate(row) for row in rows]
        required = "assistant" if self.review_mode == "assistant" else "human"
        if any(label.provenance != required for label in labels):
            raise ValueError(
                "ASSISTANT_LABELS_REQUIRED"
                if required == "assistant"
                else "ACTUAL_HUMAN_LABELS_REQUIRED"
            )
        return rows, digest(rows)

    def import_calibration_labels(self, packet_id, file):
        state = self.state
        if state["frozen"]:
            raise ValueError("STUDY_FROZEN")
        if state["pending"]:
            raise ValueError("STUDY_STAGE_REQUIRED_OR_INTERRUPTED")
        if state["status"] not in [
            "calibration_review",
            "calibration_labelled",
            "calibration_scored",
        ]:
            raise ValueError("STUDY_STAGE_REQUIRED")
        rows, label_digest = self._labels(packet_id, file, "calibration")
        record = self.service.import_labels(packet_id, rows)
        self._write(
            _expected=state,
            calibration_label_id=record["id"],
            calibration_labels_digest=label_digest,
            status="calibration_labelled",
        )
        return {**record, "next_action": "judge_calibration"}

    def _items(self, packet_id):
        packet = self.repository.get_packet(packet_id)
        definitions = {value.item_id: value for value in self.service.dataset.review_items}
        items = [
            self.service._item(
                self.service.read_run(binding["run_id"]), item_id, definitions[item_id]
            )
            for item_id, binding in packet.bindings.items()
        ]
        if any(
            digest(item.visible()) != packet.payload["item_digests"][item.item_id] for item in items
        ):
            raise ValueError("REVIEW_ITEM_CHANGED")
        return items

    def judge_calibration(self):
        if (
            self.state["status"] not in ["calibration_labelled", "calibration_scored"]
            or not self.state["calibration_label_id"]
        ):
            raise ValueError("STUDY_STAGE_REQUIRED")
        judge = self._judge("calibration")
        key = "judge_calibration:" + judge.settings_digest
        if key in self.state["results"]:
            self._write(status="calibration_scored")
            return self.state["results"][key]
        self._require("calibration")

        def work():
            items = self._items(self.state["results"]["capture_calibration"]["packet_id"])
            results = []
            for item in items:
                result = judge_saved_item(item, judge, 1).model_dump(mode="json")
                results.append(result)
                self._write(calibration_judgments=list(results))
                if result["usage"]["state"] == "unknown":
                    raise ValueError("USAGE_UNRESOLVED")
            return {
                "mode": "live",
                "judgments": results,
                "next_action": "freeze_or_revise_calibration_judge",
            }

        return self._operation(
            key, ["calibration_labelled", "calibration_scored"], "calibration_scored", work
        )

    def revise_judge(self, settings):
        state = self.state
        if state["frozen"]:
            raise ValueError("STUDY_FROZEN")
        if state["pending"]:
            raise ValueError("STUDY_STAGE_REQUIRED_OR_INTERRUPTED")
        if state["status"] not in ["calibration_labelled", "calibration_scored"]:
            raise ValueError("STUDY_STAGE_REQUIRED")
        if (
            set(settings) != {"instructions"}
            or not isinstance(settings["instructions"], str)
            or not settings["instructions"].strip()
        ):
            raise ValueError("JUDGE_SETTINGS")
        if state["judge_settings"] == settings:
            return self.report()
        if len(state["judge_revisions"]) >= 2:
            raise ValueError("REVISION_LIMIT")
        self._write(
            _expected=state,
            judge_settings=settings,
            judge_revisions=state["judge_revisions"] + [digest(settings)],
            status="calibration_labelled",
        )
        return {"revisions": len(self.state["judge_revisions"]), "next_action": "judge_calibration"}

    def calibration_development(self, round_number):
        if self.state["frozen"]:
            raise ValueError("STUDY_FROZEN")
        if round_number not in [1, 2]:
            raise ValueError("CALIBRATION_DEVELOPMENT_LIMIT")
        self._require("calibration_development", capture=True)
        key = f"calibration_development_{round_number}"
        return self._operation(
            key,
            ["calibration_labelled", "calibration_scored"],
            self.state["status"],
            lambda: {
                "run_ids": self._natural_batch(
                    "calibration", "candidate", "calibration_development", key
                ),
                "scope": "calibration diagnostics only; original labels unchanged",
            },
        )

    def freeze(self):
        if "freeze" in self.state["results"]:
            return self.state["results"]["freeze"]
        if self.ledger.summary()["unsettled_calls"]:
            raise ValueError("USAGE_UNRESOLVED")

        def work():
            identity = self._identity()
            self._write(frozen=identity)
            return {"identity_digest": digest(identity), "next_action": "capture_holdout"}

        return self._operation("freeze", ["calibration_scored"], "frozen", work)

    def capture_holdout(self):
        if "capture_heldout" in self.state["results"]:
            return self.state["results"]["capture_heldout"]
        if self.state["status"] != "frozen":
            raise ValueError("STUDY_STAGE_REQUIRED")
        self._verify_freeze()
        self._require("heldout", capture=True)
        return self._operation(
            "capture_heldout", ["frozen"], "heldout_review", lambda: self._review_capture("heldout")
        )

    def qualify_holdout(self, packet_id, file):
        if self.state["status"] not in [
            "heldout_review",
            "qualified",
            "qualification_failed",
            "released",
        ]:
            raise ValueError("STUDY_STAGE_REQUIRED")
        rows, label_digest = self._labels(packet_id, file, "heldout")
        if "qualify_holdout" in self.state["results"]:
            if label_digest != self.state["heldout_labels_digest"]:
                raise ValueError("HOLDOUT_LABELS_FROZEN")
            return self.state["results"]["qualify_holdout"]
        self._verify_freeze()
        self._require("heldout")

        def work():
            imported = self.service.import_labels(packet_id, rows)
            self._write(heldout_label_id=imported["id"], heldout_labels_digest=label_digest)
            judge = self._judge("heldout")
            results = []
            for item in self._items(packet_id):
                for repetition in [1, 2]:
                    result = judge_saved_item(item, judge, repetition)
                    results.append(result)
                    self._write(
                        heldout_judgments=[value.model_dump(mode="json") for value in results]
                    )
                    if result.usage.state == "unknown":
                        raise ValueError("USAGE_UNRESOLVED")
            record = self.repository.save_qualification(
                imported["id"], results, self.service.dataset
            )
            return {
                "id": record.id,
                "qualification": record.payload,
                "next_action": "capture_release_if_qualified",
            }

        result = self._operation("qualify_holdout", ["heldout_review"], "qualified", work)
        if result["qualification"]["status"] != "pass":
            self._write(status="qualification_failed")
        return result

    def capture_release(self):
        if "capture_release" in self.state["results"]:
            return self.state["results"]["capture_release"]
        qualification = self.state["results"].get("qualify_holdout")
        if not qualification or qualification["qualification"]["status"] != "pass":
            raise ValueError("JUDGE_QUALIFICATION_REQUIRED")
        self._verify_freeze()
        self._require("release", capture=True)
        self._require("release")

        def work():
            baseline = self._natural_batch("release", "baseline", "release", "release_baseline")
            candidate = self._natural_batch("release", "candidate", "release", "release_candidate")
            exact = [self._derive(run, "change_money") for run in candidate]
            semantic = [self._derive(run, "unsupported_cause") for run in candidate]
            service = EvaluationService(
                self.repository, self.root, self._judge("release"), review_mode=self.review_mode
            )
            baseline_record = service.evaluate(baseline)
            self._write(evaluations={"baseline": baseline_record["id"]})
            complete = baseline_record["evaluation"]["usage_complete"]
            base = baseline_record["id"]
            decisions = {}
            for name, runs in [
                ("candidate", candidate),
                ("exact_control", exact),
                ("semantic_control", semantic),
            ]:
                evaluated = service.evaluate(runs, run_judges=complete)
                self._write(
                    evaluations={**self.state.get("evaluations", {}), name: evaluated["id"]}
                )
                complete = complete and evaluated["evaluation"]["usage_complete"]
                decisions[name] = service.compare(base, evaluated["id"], qualification["id"])
                self._write(release_decisions=dict(decisions))
            if not complete:
                raise ValueError("LIVE_EVALUATION_INCOMPLETE")
            return decisions

        return self._operation("capture_release", ["qualified"], "released", work)

    def report(self):
        summary = self.ledger.summary()
        return {
            **self.state,
            "study_id": self.id,
            "config_digest": self.config_digest,
            "ledger": {
                **summary,
                "subject_attempts": sum(r["kind"] == "subject" for r in summary["calls"]),
                "judge_attempts": sum(r["kind"] == "judge" for r in summary["calls"]),
            },
            "limits": (
                "Assistant reference labels; human agreement is unmeasured. Paired controls and prior implementation context limit independence. A failed qualification/candidate remains a measured failure."
                if self.review_mode == "assistant"
                else "One human reviewer; paired controls are not independent observations. A failed qualification/candidate remains a measured failure."
            ),
        }
