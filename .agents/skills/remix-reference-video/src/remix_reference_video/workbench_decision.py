"""Workbench decision adapter over the authoritative ApprovalService."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .approvals import ApprovalError, ApprovalService
from .review_session import ReviewSessionService
from .storage import StorageError, TaskStorage, atomic_write_json, read_json_object


class WorkbenchConflict(StorageError):
    def __init__(self, message: str, *, current_revision: int, refresh_path: str) -> None:
        super().__init__(message); self.current_revision = current_revision; self.refresh_path = refresh_path


_SCOPES = {
    "gate1":"artifact_set", "gate2":"artifact_set", "gate3_material_selection":"fragment_set",
    "gate3_evidence_closure":"artifact_set", "gate4_pre_generation":"script_settings",
    "gate4_post_generation":"output_bundle", "gate5":"output_bundle",
}
_DECISIONS = {"approve":"approved", "reject":"rejected", "request_changes":"changes_requested", "approved":"approved", "rejected":"rejected", "changes_requested":"changes_requested"}


class WorkbenchDecisionService:
    def __init__(self, task_root: Path, *, actor: str, role: str = "operator") -> None:
        self.root = Path(task_root).resolve(strict=True); self.actor = actor.strip()
        self.storage = TaskStorage(self.root); self.sessions = ReviewSessionService(self.root, actor=self.actor, role=role)

    def submit(self, *, session_id: str, gate_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if gate_id not in _SCOPES: raise WorkbenchConflict("unsupported Gate", current_revision=self._revision(), refresh_path=self._refresh(gate_id))
        key = payload.get("idempotency_key")
        if not isinstance(key, str) or not key: raise WorkbenchConflict("idempotency key is required", current_revision=self._revision(), refresh_path=self._refresh(gate_id))
        normalized = self._normalize(gate_id, payload)
        digest = self._payload_hash(normalized)
        ledger = self._ledger_path(key)
        if ledger.is_file():
            existing = read_json_object(ledger)
            if existing.get("payload_sha256") != digest:
                raise WorkbenchConflict("idempotency conflict", current_revision=self._revision(), refresh_path=self._refresh(gate_id))
            return dict(existing["result"])
        session = self.sessions.get(session_id); identity = session["review_identity"]
        if identity.get("gate_id") != gate_id:
            raise WorkbenchConflict("session Gate mismatch", current_revision=self._revision(), refresh_path=self._refresh(gate_id))
        state = self.storage.read_state()
        self.sessions.record_server_event(session_id, "review.decision_submitted", {"decision": normalized["decision"]})
        current_revision = int(state["state_revision"])
        if normalized["state_revision"] != current_revision or normalized["review_package_hash"] != identity.get("review_package_hash"):
            self._conflicted(session_id, gate_id, current_revision, "review identity changed")
            raise WorkbenchConflict("review identity changed", current_revision=current_revision, refresh_path=self._refresh(gate_id))
        request_dir = self.root / "workbench" / "decision_requests"; request_dir.mkdir(parents=True, exist_ok=True)
        decision_path = request_dir / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
        atomic_write_json(decision_path, {"decision":normalized["decision"],"scope_type":_SCOPES[gate_id],"scope_ids":normalized["scope_ids"],"strategy":normalized["strategy"],"note":normalized.get("note")})
        try:
            result = ApprovalService(self.storage).approve(gate_id=gate_id, review_package_hash=normalized["review_package_hash"], decision_file=decision_path, actor=self.actor)
        except ApprovalError as error:
            self._conflicted(session_id, gate_id, self._revision(), str(error))
            raise WorkbenchConflict(str(error), current_revision=self._revision(), refresh_path=self._refresh(gate_id)) from error
        updated_revision = self._revision()
        self.storage.append_event({"event_type":"review.decision_accepted","session_id":session_id,"run_id":identity["run_id"],"gate_id":gate_id,"decision_id":result["decision_id"],"actor":self.actor}, state_revision=updated_revision)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(ledger, {"idempotency_key":key,"payload_sha256":digest,"result":result})
        return result

    def _normalize(self, gate_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        decision = _DECISIONS.get(payload.get("decision"))
        scope_ids = payload.get("scope_ids"); strategy = payload.get("strategy")
        if decision is None or not isinstance(scope_ids, list) or not scope_ids or any(not isinstance(item, str) or not item for item in scope_ids) or not isinstance(strategy, Mapping):
            raise WorkbenchConflict("decision payload is invalid", current_revision=self._revision(), refresh_path=self._refresh(gate_id))
        revision = payload.get("state_revision"); package_hash = payload.get("review_package_hash")
        if isinstance(revision, bool) or not isinstance(revision, int) or not isinstance(package_hash, str):
            raise WorkbenchConflict("review binding is invalid", current_revision=self._revision(), refresh_path=self._refresh(gate_id))
        return {"decision":decision,"scope_ids":scope_ids,"strategy":dict(strategy),"note":payload.get("note"),"review_package_hash":package_hash,"state_revision":revision}

    def _conflicted(self, session_id: str, gate_id: str, revision: int, reason: str) -> None:
        state = self.storage.read_state()
        self.storage.append_event({"event_type":"review.decision_conflicted","session_id":session_id,"run_id":state.get("run_id"),"gate_id":gate_id,"reason":reason,"actor":self.actor}, state_revision=revision)

    def _revision(self) -> int: return int(self.storage.read_state()["state_revision"])
    @staticmethod
    def _payload_hash(value: Mapping[str, Any]) -> str: return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    def _ledger_path(self, key: str) -> Path: return self.root / "workbench" / "idempotency" / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
    @staticmethod
    def _refresh(gate_id: str) -> str: return f"/api/v1/runs/current/gates/{gate_id}/review"
