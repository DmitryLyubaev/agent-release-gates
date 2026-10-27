import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field, StrictBool, StrictInt, StrictStr

from agent_release_gates.artifacts.store import canonical, digest
from agent_release_gates.contracts.artifacts import Digest, Identifier, StrictModel, utc

Stage = Literal["calibration", "calibration_development", "heldout", "release"]


class AllowanceConfig(StrictModel):
    allowance_id: Identifier
    study_id: Identifier
    project_root: StrictStr
    ledger_path: StrictStr
    provider: Literal["anthropic"]
    model: Literal["claude-sonnet-5-5"]
    price_id: StrictStr = Field(min_length=1)
    input_nano_usd_per_token: Literal[2000]
    output_nano_usd_per_token: Literal[10000]
    cap_nano_usd: StrictInt = Field(gt=0, le=10_000_000_000)
    max_subject_attempts: StrictInt = Field(gt=0, le=168)
    max_judge_attempts: StrictInt = Field(gt=0, le=96)
    max_investigations: StrictInt = Field(gt=0, le=28)
    max_calibration_development: StrictInt = Field(ge=0, le=8)
    dataset_digest: Digest


class AllowanceApproval(StrictModel):
    config: AllowanceConfig
    config_digest: Digest
    approved: StrictBool
    approved_by: StrictStr = Field(min_length=1)
    approved_at: StrictStr
    personal_account_confirmed: StrictBool
    budget_alert_ready: StrictBool
    allowed_stages: list[Stage] = Field(min_length=1)


def validate_approval(raw: dict) -> AllowanceApproval:
    try:
        approval = AllowanceApproval.model_validate(raw)
        utc(approval.approved_at)
        if not all(
            [
                approval.approved,
                approval.approved_by.strip(),
                approval.personal_account_confirmed,
                approval.budget_alert_ready,
                digest(raw["config"]) == approval.config_digest,
            ]
        ):
            raise ValueError
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("APPROVAL_REQUIRED_OR_CHANGED") from error
    return approval


class BudgetLedger:
    """One allowance, one canonical path; pending calls fail closed across restarts."""

    def __init__(self, path: Path, approval: dict):
        self.approval = validate_approval(approval)
        self.config = self.approval.config
        self.path = Path(path).resolve()
        root = Path(self.config.project_root).resolve()
        expected = root / ".local" / "live" / self.config.allowance_id / "budget.sqlite"
        protected = "payments-reconciliation-assistant" in {p.lower() for p in root.parts}
        protected = protected or any(
            root.parts[i : i + 2] == (".local", "subject") for i in range(len(root.parts) - 1)
        )
        if (
            protected
            or self.path != expected.resolve()
            or self.path != Path(self.config.ledger_path).resolve()
        ):
            raise ValueError("LEDGER_PATH")
        # A symlink under .local must not redirect evidence/allowance into another checkout.
        if not self.path.is_relative_to(root) or expected.resolve() != expected:
            raise ValueError("LEDGER_PATH")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS allowance (id INTEGER PRIMARY KEY, digest TEXT NOT NULL)"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY, attempt_key TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
                investigation TEXT, stage TEXT NOT NULL, turn INTEGER, reserved INTEGER NOT NULL,
                charge INTEGER, usage TEXT, request_id TEXT, metadata TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(kind, investigation, turn))""")
            connection.execute(
                "INSERT OR IGNORE INTO allowance VALUES (1,?)", (self.approval.config_digest,)
            )
            if (
                connection.execute("SELECT digest FROM allowance WHERE id=1").fetchone()[0]
                != self.approval.config_digest
            ):
                raise ValueError("ALLOWANCE_CHANGED")

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def reserve(
        self, *, attempt_key: str, kind: str, investigation_id: str | None, metadata: dict
    ) -> str:
        if not isinstance(attempt_key, str) or not re.fullmatch(
            r"[A-Za-z0-9_:.-]{1,200}", attempt_key
        ):
            raise ValueError("ATTEMPT_KEY")
        if kind not in ["subject", "judge"]:
            raise ValueError("ATTEMPT_KIND")
        stage = metadata.get("stage")
        if stage not in self.approval.allowed_stages:
            raise ValueError("STAGE_NOT_APPROVED")
        turn = metadata.get("turn") if kind == "subject" else None
        if kind == "subject" and (
            not investigation_id or type(turn) is not int or not 0 <= turn < 6
        ):
            raise ValueError("SUBJECT_LIMIT")
        reserved = 2_040_960_000 if kind == "subject" else 2_010_240_000
        with self.transaction() as connection:
            rows = connection.execute("SELECT * FROM attempts").fetchall()
            if any(row["attempt_key"] == attempt_key for row in rows):
                raise ValueError("ATTEMPT_ALREADY_DISPATCHED")
            if any(row["charge"] is None for row in rows):
                raise ValueError("UNSETTLED_CALL")
            if sum(row["charge"] for row in rows) + reserved > self.config.cap_nano_usd:
                raise ValueError("BUDGET_LIMIT")
            count = sum(row["kind"] == kind for row in rows)
            maximum = (
                self.config.max_subject_attempts
                if kind == "subject"
                else self.config.max_judge_attempts
            )
            investigations = {row["investigation"] for row in rows if row["kind"] == "subject"}
            development = {
                row["investigation"]
                for row in rows
                if row["stage"] == "calibration_development" and row["kind"] == "subject"
            }
            if (
                count >= maximum
                or (
                    kind == "subject"
                    and investigation_id not in investigations
                    and len(investigations) >= self.config.max_investigations
                )
                or (
                    kind == "subject"
                    and stage == "calibration_development"
                    and investigation_id not in development
                    and len(development) >= self.config.max_calibration_development
                )
            ):
                raise ValueError("COUNT_LIMIT")
            identity = str(uuid4())
            try:
                connection.execute(
                    "INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        identity,
                        attempt_key,
                        kind,
                        investigation_id,
                        stage,
                        turn,
                        reserved,
                        None,
                        None,
                        None,
                        canonical(metadata).decode(),
                        datetime.now(UTC).isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("ATTEMPT_ALREADY_DISPATCHED") from error
            return identity

    def settle(self, reservation_id: str, usage: dict, request_id: str) -> dict:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM attempts WHERE id=?", (reservation_id,)
            ).fetchone()
            if row is None:
                raise ValueError("RESERVATION_REQUIRED")
            allowed = {
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
                "service_tier",
                "inference_geo",
                "server_tool_use",
                "cache_creation",
            }
            if not isinstance(usage, dict) or set(usage) - allowed:
                raise ValueError("INVALID_USAGE")
            maximum = 4096 if row["kind"] == "subject" else 1024
            if any(
                type(usage.get(k)) is not int or not 0 <= usage[k] <= limit
                for k, limit in [("input_tokens", 1_000_000), ("output_tokens", maximum)]
            ):
                raise ValueError("INVALID_USAGE")
            if any(
                usage.get(k, 0) != 0
                for k in ["cache_creation_input_tokens", "cache_read_input_tokens"]
            ):
                raise ValueError("UNPRICED_USAGE")
            if (
                usage.get("service_tier", "standard") != "standard"
                or usage.get("inference_geo", "global") != "global"
            ):
                raise ValueError("UNPRICED_USAGE")
            for key in ["server_tool_use", "cache_creation"]:
                value = usage.get(key)
                if value is not None and (
                    not isinstance(value, dict) or any(v != 0 for v in value.values())
                ):
                    raise ValueError("UNPRICED_USAGE")
            if not isinstance(request_id, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,200}", request_id
            ):
                raise ValueError("INVALID_USAGE_RECEIPT")
            charge = usage["input_tokens"] * 2000 + usage["output_tokens"] * 10000
            serialized = canonical(usage).decode()
            if row["charge"] is not None and (row["charge"], row["usage"], row["request_id"]) != (
                charge,
                serialized,
                request_id,
            ):
                raise ValueError("USAGE_CONFLICT")
            connection.execute(
                "UPDATE attempts SET charge=?,usage=?,request_id=? WHERE id=?",
                (charge, serialized, request_id, reservation_id),
            )
        return {"reservation_id": reservation_id, "cost_nano_usd": charge}

    def summary(self) -> dict:
        with self.transaction() as connection:
            rows = [
                dict(row) for row in connection.execute("SELECT * FROM attempts ORDER BY rowid")
            ]
        return {
            "allowance_digest": self.approval.config_digest,
            "cap_nano_usd": self.config.cap_nano_usd,
            "spent_nano_usd": sum(row["charge"] or 0 for row in rows),
            "committed_nano_usd": sum(
                row["charge"] if row["charge"] is not None else row["reserved"] for row in rows
            ),
            "unsettled_calls": sum(row["charge"] is None for row in rows),
            "calls": [
                {
                    **row,
                    "usage": json.loads(row["usage"]) if row["usage"] else None,
                    "metadata": json.loads(row["metadata"]),
                }
                for row in rows
            ],
        }
