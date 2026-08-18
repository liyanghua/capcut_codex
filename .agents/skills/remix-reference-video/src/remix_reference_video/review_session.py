"""Actor-bound review sessions and trusted timing intent events."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .storage import StorageError, TaskStorage, atomic_write_json, read_json_object, read_jsonl_records


class ReviewSessionError(StorageError):
    pass


_CLIENT_EVENTS = frozenset({
    "review.active_start", "review.evidence_interaction", "review.active_stop",
    "review.heartbeat", "review.pause",
})
_SERVER_EVENTS = frozenset({
    "review.change_previewed", "review.decision_submitted", "review.decision_accepted",
    "review.decision_conflicted", "review.rework_completed",
})
_CLIENT_DURATION_FIELDS = frozenset({"seconds", "duration_seconds", "elapsed_seconds", "at_seconds"})


class ReviewSessionService:
    def __init__(self, task_root: Path, *, actor: str, role: str = "operator") -> None:
        if not isinstance(actor, str) or not actor.strip():
            raise ReviewSessionError("actor is required")
        if role not in {"operator", "owner"}:
            raise ReviewSessionError("role is unsupported")
        self.root = Path(task_root).resolve(strict=True)
        self.actor = actor.strip(); self.role = role; self.storage = TaskStorage(self.root)

    def open(self, gate_id: str) -> dict[str, Any]:
        state = self.storage.read_state(); package_path = self._package_path(gate_id)
        package = read_json_object(package_path)
        if package.get("run_id") != state.get("run_id") or package.get("state_revision") != state.get("state_revision"):
            raise ReviewSessionError("review package is stale")
        session_id = str(uuid.uuid4())
        identity = {"session_id": session_id, "run_id": state["run_id"], "gate_id": gate_id, "review_package_hash": self.package_hash(gate_id), "state_revision": state["state_revision"], "actor": self.actor, "role": self.role}
        record = {"session_id": session_id, "review_identity": identity, "actor": self.actor, "role": self.role, "created_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")}
        directory = self.root / "workbench" / "sessions"; directory.mkdir(parents=True, exist_ok=True)
        atomic_write_json(directory / f"{session_id}.json", record)
        self.storage.append_event({"event_type":"review.opened","session_id":session_id,"run_id":state["run_id"],"gate_id":gate_id,"actor":self.actor}, state_revision=int(state["state_revision"]))
        return record

    def record_intent(self, session_id: str, event_type: str, payload: Mapping[str, object] | None = None) -> dict[str, Any]:
        if event_type in _SERVER_EVENTS:
            raise ReviewSessionError("event type is server-owned")
        if event_type not in _CLIENT_EVENTS:
            raise ReviewSessionError("event type is unsupported")
        return self._record(session_id, event_type, payload)

    def record_server_event(self, session_id: str, event_type: str, payload: Mapping[str, object] | None = None) -> dict[str, Any]:
        if event_type not in _SERVER_EVENTS:
            raise ReviewSessionError("event type is not server-owned")
        return self._record(session_id, event_type, payload)

    def _record(self, session_id: str, event_type: str, payload: Mapping[str, object] | None = None) -> dict[str, Any]:
        record = self._session(session_id); payload = dict(payload or {})
        if _CLIENT_DURATION_FIELDS.intersection(payload):
            raise ReviewSessionError("client duration fields are forbidden")
        if any(not isinstance(key, str) for key in payload):
            raise ReviewSessionError("event payload keys must be strings")
        state = self.storage.read_state(); identity = record["review_identity"]
        if state.get("run_id") != identity["run_id"] or state.get("state_revision") != identity["state_revision"]:
            raise ReviewSessionError("session identity is stale")
        events = read_jsonl_records(self.root / "pipeline_events.jsonl")
        session_events = [item for item in events if item.get("session_id") == session_id]
        if any(item.get("event_type") == "review.pause" for item in session_events):
            raise ReviewSessionError("session is paused")
        if session_events:
            last = self._parse_time(session_events[-1].get("occurred_at"))
            if last is not None and (datetime.now(UTC) - last).total_seconds() > 60:
                raise ReviewSessionError("session heartbeat expired")
        return self.storage.append_event({"event_type":event_type,"session_id":session_id,"run_id":identity["run_id"],"gate_id":identity["gate_id"],"actor":self.actor,"payload":payload}, state_revision=int(state["state_revision"]))

    def package_hash(self, gate_id: str) -> str:
        path = self._package_path(gate_id)
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def get(self, session_id: str) -> dict[str, Any]:
        return self._session(session_id)

    def _session(self, session_id: str) -> dict[str, Any]:
        if not isinstance(session_id, str) or not session_id or Path(session_id).name != session_id:
            raise ReviewSessionError("session is invalid")
        path = self.root / "workbench" / "sessions" / f"{session_id}.json"
        if path.is_symlink() or not path.is_file():
            raise ReviewSessionError("session is unknown")
        record = read_json_object(path)
        if record.get("actor") != self.actor or record.get("role") != self.role:
            raise ReviewSessionError("session actor mismatch")
        return record

    def _package_path(self, gate_id: str) -> Path:
        if not isinstance(gate_id, str) or not gate_id or Path(gate_id).name != gate_id:
            raise ReviewSessionError("gate is invalid")
        path = self.root / "gate_review_packages" / f"{gate_id}.json"
        if path.is_symlink() or not path.is_file():
            raise ReviewSessionError("review package is missing")
        return path

    @staticmethod
    def _parse_time(value: object) -> datetime | None:
        if not isinstance(value, str): return None
        try: return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError: return None
