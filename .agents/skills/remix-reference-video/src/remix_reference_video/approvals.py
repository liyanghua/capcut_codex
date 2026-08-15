"""Hash-bound, trusted-time Gate approvals for Track B production."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .contracts import CANONICAL_GATE_IDS, PRODUCTION_EXECUTION_MODE
from .storage import StorageError, TaskStorage, atomic_write_json, read_json_object
from .transactions import ArtifactPromotion, TransactionManager


class ApprovalError(StorageError):
    """Raised when an approval request is stale, malformed, or unauthorized."""


_DECISIONS = frozenset({"approved", "rejected", "changes_requested"})
_SCOPES = frozenset({"artifact_set", "fragment_set", "script_settings", "output_bundle"})
_DECISION_FIELDS = frozenset({"decision", "scope_type", "scope_ids", "strategy", "note"})
_REQUIRED_DECISION_FIELDS = frozenset({"decision", "scope_type", "scope_ids", "strategy"})
_PREDECESSORS = {
    "gate2": ("gate1",),
    "gate3_material_selection": ("gate1", "gate2"),
    "gate3_evidence_closure": ("gate1", "gate2", "gate3_material_selection"),
    "gate4_pre_generation": ("gate1", "gate2", "gate3"),
    "gate4_post_generation": ("gate1", "gate2", "gate3", "gate4_pre_generation"),
    "gate5": ("gate1", "gate2", "gate3", "gate4"),
}


class ApprovalService:
    def __init__(self, storage: TaskStorage) -> None:
        self.storage = storage
        self.root = storage.task_root
        self.transactions = TransactionManager(storage)

    def approve(
        self,
        *,
        gate_id: str,
        review_package_hash: str,
        decision_file: Path,
        actor: str,
    ) -> dict[str, Any]:
        if gate_id not in CANONICAL_GATE_IDS:
            raise ApprovalError(f"unsupported gate: {gate_id}")
        if not isinstance(actor, str) or not actor.strip():
            raise ApprovalError("actor is required")
        if not self._is_sha256(review_package_hash):
            raise ApprovalError("review package hash must be SHA-256")
        decision = self._read_decision(decision_file)
        package_path = self.root / "gate_review_packages" / f"{gate_id}.json"
        if self._sha256(package_path) != review_package_hash:
            raise ApprovalError("review package hash mismatch")
        package = read_json_object(package_path)
        state = self.storage.read_state()
        if state.get("execution_mode") != PRODUCTION_EXECUTION_MODE:
            raise ApprovalError("approve-gate only accepts track-b-production tasks")
        decision_key = self._decision_key(
            gate_id, review_package_hash, decision, actor.strip()
        )
        existing = self._existing_decision(state, decision_key)
        if existing is not None:
            return existing
        if package.get("run_id") != state.get("run_id"):
            raise ApprovalError("review package run does not match task run")
        if package.get("gate_id") != gate_id:
            raise ApprovalError("review package gate does not match request")
        revision = state.get("state_revision")
        if package.get("state_revision") != revision:
            raise ApprovalError("review package revision is stale")
        created_at = self._timestamp(package.get("created_at"), "review package created_at")
        now = datetime.now(UTC)
        if created_at > now:
            raise ApprovalError("review package timestamp is out of order")
        self._verify_inputs(package.get("input_hashes"))
        if decision["decision"] == "approved":
            self._verify_predecessors(state, gate_id)
        approved_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        record: dict[str, Any] = {
            "decision_id": f"approval-{decision_key[:24]}",
            "decision_key": decision_key,
            "gate_id": gate_id,
            "decision": decision["decision"],
            "scope_type": decision["scope_type"],
            "scope_ids": decision["scope_ids"],
            "strategy": decision["strategy"],
            "note": decision.get("note"),
            "actor": actor.strip(),
            "approved_at": approved_at,
            "review_package_hash": review_package_hash,
            "input_hashes": package["input_hashes"],
            "state_revision_before": revision,
        }
        gates = dict(state.get("gate_status", {}))
        decisions = [*state.get("decisions", []), record]
        gates[gate_id] = self._gate_status_for_decision(str(decision["decision"]))
        self._summarize(gates, "gate3", "gate3_material_selection", "gate3_evidence_closure")
        self._summarize(gates, "gate4", "gate4_pre_generation", "gate4_post_generation")
        state_changes: dict[str, object] = {
            "gate_status": gates,
            "decisions": decisions,
        }
        promotions: tuple[ArtifactPromotion, ...] = ()
        if gate_id == "gate4_pre_generation" and decision["decision"] == "approved":
            promotion, artifact = self._stage_approved_script(record, decision)
            promotions = (promotion,)
            state_changes["artifacts"] = {
                **dict(state.get("artifacts", {})),
                "approved_production_script": artifact,
            }
        transaction_id = f"approval-{decision_key[:24]}"
        self.transactions.prepare(
            transaction_id=transaction_id,
            expected_revision=int(revision),
            state_changes=state_changes,
            event={
                "event_type": "gate.decision.recorded",
                "gate_id": gate_id,
                "decision_id": record["decision_id"],
            },
            metric=None,
            promotions=promotions,
        )
        self.transactions.commit(transaction_id)
        record["state_revision_after"] = int(revision) + 1
        return record

    def _read_decision(self, path: Path) -> dict[str, Any]:
        resolved = self._task_file(path, "decision file")
        value = read_json_object(resolved)
        fields = frozenset(value)
        if not _REQUIRED_DECISION_FIELDS <= fields or fields - _DECISION_FIELDS:
            raise ApprovalError("decision file has invalid fields")
        if value.get("decision") not in _DECISIONS:
            raise ApprovalError("decision is unsupported")
        if value.get("scope_type") not in _SCOPES:
            raise ApprovalError("scope_type is unsupported")
        scope_ids = value.get("scope_ids")
        if (
            not isinstance(scope_ids, list)
            or not scope_ids
            or any(not isinstance(item, str) or not item.strip() for item in scope_ids)
        ):
            raise ApprovalError("scope_ids must be a non-empty string array")
        if not isinstance(value.get("strategy"), Mapping):
            raise ApprovalError("strategy must be an object")
        if value.get("note") is not None and not isinstance(value.get("note"), str):
            raise ApprovalError("note must be a string")
        return value

    def _verify_inputs(self, raw_hashes: object) -> None:
        if not isinstance(raw_hashes, Mapping) or not raw_hashes:
            raise ApprovalError("review package input_hashes must be non-empty")
        for relative, expected in raw_hashes.items():
            if not isinstance(relative, str) or not self._is_sha256(expected):
                raise ApprovalError("review package input hash is invalid")
            path = self._task_file(self.root / relative, "review input")
            if self._sha256(path) != expected:
                raise ApprovalError(f"review input hash mismatch: {relative}")

    def _verify_predecessors(self, state: Mapping[str, object], gate_id: str) -> None:
        gates = state.get("gate_status")
        if not isinstance(gates, Mapping):
            raise ApprovalError("gate_status must be an object")
        missing = [gate for gate in _PREDECESSORS.get(gate_id, ()) if gates.get(gate) != "approved"]
        if missing:
            raise ApprovalError(
                f"cannot approve {gate_id} before: {', '.join(missing)}"
            )

    def _stage_approved_script(
        self, record: Mapping[str, object], decision: Mapping[str, object]
    ) -> tuple[ArtifactPromotion, dict[str, str]]:
        strategy = decision.get("strategy")
        settings = strategy.get("tts_settings") if isinstance(strategy, Mapping) else None
        if not isinstance(settings, Mapping) or not settings:
            raise ApprovalError("gate4_pre_generation requires tts_settings")
        candidate_path = self._task_file(
            self.root / "production_script_candidate.json", "script candidate"
        )
        candidate = read_json_object(candidate_path)
        approved = {
            **candidate,
            "artifact_type": "approved_production_script",
            "schema_id": "urn:capcut:remix-reference-video:artifact:approved-production-script",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "lifecycle_status": "approved",
            "tts_settings": dict(settings),
            "approval": dict(record),
        }
        transaction_id = str(record["decision_id"])
        staged = self.root / ".staging" / transaction_id / "approved_production_script.json"
        atomic_write_json(staged, approved)
        with staged.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        final = self.root / "approved_production_script.json"
        return (
            ArtifactPromotion(
                staged_path=staged,
                final_path=final,
                expected_type="approved_production_script",
            ),
            {"path": "approved_production_script.json", "sha256": digest},
        )

    def _task_file(self, path: Path, context: str) -> Path:
        requested = Path(path)
        if requested.is_symlink():
            raise ApprovalError(f"{context} must not be a symlink")
        try:
            resolved = requested.resolve(strict=True)
        except OSError as error:
            raise ApprovalError(f"{context} is missing") from error
        if resolved != self.root and self.root not in resolved.parents:
            raise ApprovalError(f"{context} escapes task root")
        if not resolved.is_file():
            raise ApprovalError(f"{context} must be a regular file")
        return resolved

    @staticmethod
    def _summarize(gates: dict[str, object], summary: str, first: str, second: str) -> None:
        if gates.get(first) == gates.get(second) == "approved":
            gates[summary] = "approved"
        elif gates.get(first) in {"rejected", "blocked", "stale"} or gates.get(second) in {"rejected", "blocked", "stale"}:
            gates[summary] = "blocked"

    @staticmethod
    def _gate_status_for_decision(decision: str) -> str:
        return "approved" if decision == "approved" else "rejected"

    @staticmethod
    def _existing_decision(
        state: Mapping[str, object], decision_key: str
    ) -> dict[str, Any] | None:
        decisions = state.get("decisions")
        if not isinstance(decisions, list):
            raise ApprovalError("decisions must be an array")
        for item in decisions:
            if isinstance(item, dict) and item.get("decision_key") == decision_key:
                return item
        return None

    @staticmethod
    def _decision_key(
        gate_id: str, package_hash: str, decision: Mapping[str, object], actor: str
    ) -> str:
        payload = json.dumps(
            {
                "gate_id": gate_id,
                "review_package_hash": package_hash,
                "decision": decision,
                "actor": actor,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _timestamp(value: object, context: str) -> datetime:
        if not isinstance(value, str):
            raise ApprovalError(f"{context} is required")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ApprovalError(f"{context} is invalid") from error
        if parsed.tzinfo is None:
            raise ApprovalError(f"{context} must include a timezone")
        return parsed.astimezone(UTC)

    @staticmethod
    def _is_sha256(value: object) -> bool:
        return isinstance(value, str) and len(value) == 64 and all(
            character in "0123456789abcdef" for character in value
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        try:
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as error:
            raise ApprovalError(f"required review file is missing: {path}") from error
