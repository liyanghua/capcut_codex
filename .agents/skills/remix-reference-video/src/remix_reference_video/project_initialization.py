"""Local, non-authoritative project drafts for Stage 0 initialization."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator, Mapping

from .storage import atomic_write_json, read_json_object


_ENVELOPE = {
    "schema_version": "1.0.0",
    "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
}
_TASK_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_REFERENCE_SUFFIXES = frozenset({".mp4", ".mov", ".m4v"})


class ProjectInitializationError(RuntimeError):
    """Raised when an initialization input is invalid."""


class ProjectInitializationConflict(ProjectInitializationError):
    """Raised for revision, idempotency, or task-root conflicts."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _normalize_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ProjectInitializationError(f"{field} must be a string")
    normalized = " ".join(unicodedata.normalize("NFC", value).split())
    if not normalized:
        raise ProjectInitializationError(f"{field} is required")
    return normalized


def _normalize_claim_texts(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ProjectInitializationError("claims must be an array")
    normalized: set[str] = set()
    for item in value:
        text = _normalize_text(item, "claim")
        if text == "无":
            continue
        normalized.add(text)
    return sorted(normalized)


def claim_objects(value: object) -> list[dict[str, str]]:
    return [
        {
            "claim_id": "claim-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
            "text": text,
        }
        for text in _normalize_claim_texts(value)
    ]


def validate_local_input_path(path: Path, *, kind: str) -> Path:
    requested = Path(path)
    if not requested.is_absolute():
        raise ProjectInitializationError(f"{kind} path must be absolute")
    current = Path(requested.anchor)
    for part in requested.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ProjectInitializationError(f"{kind} path must not contain a symlink")
    try:
        resolved = requested.resolve(strict=True)
    except OSError as error:
        raise ProjectInitializationError(f"{kind} path is missing") from error
    if not os.access(resolved, os.R_OK):
        raise ProjectInitializationError(f"{kind} path is not readable")
    if kind == "reference":
        if not resolved.is_file():
            raise ProjectInitializationError("reference path must be a regular file")
        if resolved.suffix.lower() not in _REFERENCE_SUFFIXES:
            raise ProjectInitializationError("reference media type is unsupported")
    elif kind == "asset_root":
        if not resolved.is_dir():
            raise ProjectInitializationError("asset_root path must be a directory")
    else:
        raise ProjectInitializationError(f"unsupported path kind: {kind}")
    return resolved


class ProjectInitializationStore:
    """Persist editable project drafts outside production task roots."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace = Path(workspace_root).resolve(strict=True)
        if not self.workspace.is_dir():
            raise ProjectInitializationError("workspace root must be a directory")
        self.projects_root = self.workspace / "workbench" / "projects"
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.workspace / "workbench" / ".project-initialization.lock"
        self._ledger_root = self.workspace / "workbench" / "project_idempotency"

    def save_draft(
        self,
        value: Mapping[str, object],
        *,
        actor: str,
        request_id: str,
        idempotency_key: str,
        project_id: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, object]:
        actor_value = _normalize_text(actor, "actor")
        request_value = _normalize_text(request_id, "request_id")
        key = _normalize_text(idempotency_key, "idempotency_key")
        normalized = self._normalize_draft(value)
        request_hash = self._payload_hash({"project_id": project_id, "draft": normalized})
        with self._lock():
            replay = self._read_idempotency(key)
            if replay is not None:
                if replay.get("request_hash") != request_hash:
                    raise ProjectInitializationConflict("idempotency key was used with different input")
                result = replay.get("result")
                if not isinstance(result, Mapping):
                    raise ProjectInitializationConflict("idempotency result is invalid")
                return dict(result)
            identifier = project_id or str(uuid.uuid4())
            if Path(identifier).name != identifier:
                raise ProjectInitializationError("project_id is invalid")
            project_root = self.projects_root / identifier
            draft_path = project_root / "initialization_draft.json"
            existing = read_json_object(draft_path) if draft_path.is_file() else None
            revision = int(existing.get("draft_revision", 0)) if existing else 0
            if expected_revision is not None and expected_revision != revision:
                raise ProjectInitializationConflict("draft revision conflict")
            if existing is not None and project_id is None:
                raise ProjectInitializationConflict("project id collision")
            now = _now()
            result = {
                **_ENVELOPE,
                "artifact_type": "project_initialization_draft",
                "schema_id": "urn:capcut:remix-reference-video:artifact:project-initialization-draft",
                "project_id": identifier,
                **normalized,
                "created_by": str(existing.get("created_by")) if existing else actor_value,
                "created_at": str(existing.get("created_at")) if existing else now,
                "updated_at": now,
                "draft_revision": revision + 1,
                "lifecycle_status": "draft",
            }
            atomic_write_json(draft_path, result)
            self._append_audit(project_root, {
                "action": "draft.saved", "actor": actor_value, "request_id": request_value,
                "idempotency_key": key, "draft_revision": revision + 1, "recorded_at": now,
            })
            self._write_idempotency(key, request_hash, result)
            return result

    def read_draft(self, project_id: str) -> dict[str, object]:
        path = self._project_root(project_id) / "initialization_draft.json"
        return read_json_object(path)

    def list_drafts(self) -> list[dict[str, object]]:
        values: list[dict[str, object]] = []
        for path in sorted(self.projects_root.glob("*/initialization_draft.json")):
            if not path.is_symlink():
                values.append(read_json_object(path))
        return values

    def reserve_task_root(self, project_id: str, *, date: str) -> Path:
        draft = self.read_draft(project_id)
        task_name = str(draft["task_name"])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise ProjectInitializationError("reservation date is invalid")
        target = self.workspace / "work" / f"{date}-{task_name}"
        with self._lock():
            if target.exists():
                reservation = target / ".project-reservation.json"
                if reservation.is_file() and read_json_object(reservation).get("project_id") == project_id:
                    return target
                raise ProjectInitializationConflict("task name is already reserved")
            target.mkdir(parents=True)
            atomic_write_json(target / ".project-reservation.json", {"project_id": project_id, "task_name": task_name})
        return target

    def _normalize_draft(self, value: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(value, Mapping):
            raise ProjectInitializationError("draft must be an object")
        task_name = _normalize_text(value.get("task_name"), "task_name")
        if not _TASK_NAME.fullmatch(task_name):
            raise ProjectInitializationError("task_name must match [a-z0-9][a-z0-9-]{0,63}")
        reference = validate_local_input_path(Path(str(value.get("reference_path", ""))), kind="reference")
        assets = validate_local_input_path(Path(str(value.get("asset_root", ""))), kind="asset_root")
        output = value.get("output")
        voice = value.get("voice")
        if not isinstance(output, Mapping) or not isinstance(voice, Mapping):
            raise ProjectInitializationError("output and voice are required")
        normalized_output = {
            "aspect_ratio": str(output.get("aspect_ratio")),
            "width": int(output.get("width", 0)), "height": int(output.get("height", 0)),
            "fps": int(output.get("fps", 0)),
        }
        if normalized_output != {"aspect_ratio": "9:16", "width": 1080, "height": 1920, "fps": 60}:
            raise ProjectInitializationError("output must be 9:16, 1080x1920, 60fps")
        speed = float(voice.get("speed", 0))
        if speed != 1.0:
            raise ProjectInitializationError("voice speed must be 1.0")
        return {
            "reference_path": str(reference), "asset_root": str(assets),
            "product_name": _normalize_text(value.get("product_name"), "product_name"),
            "task_name": task_name,
            "platform": _normalize_text(value.get("platform"), "platform"),
            "audience": _normalize_text(value.get("audience"), "audience"),
            "approved_claims": _normalize_claim_texts(value.get("approved_claims", [])),
            "forbidden_claims": _normalize_claim_texts(value.get("forbidden_claims", [])),
            "output": normalized_output,
            "voice": {
                "provider": _normalize_text(voice.get("provider"), "voice.provider"),
                "speaker": _normalize_text(voice.get("speaker"), "voice.speaker"),
                "speed": speed,
            },
        }

    def _project_root(self, project_id: str) -> Path:
        if not isinstance(project_id, str) or Path(project_id).name != project_id:
            raise ProjectInitializationError("project_id is invalid")
        path = self.projects_root / project_id
        if path.is_symlink() or not path.is_dir():
            raise ProjectInitializationError("project is unknown")
        return path

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self._lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _read_idempotency(self, key: str) -> dict[str, object] | None:
        path = self._ledger_root / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
        return read_json_object(path) if path.is_file() else None

    def _write_idempotency(self, key: str, request_hash: str, result: Mapping[str, object]) -> None:
        path = self._ledger_root / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
        atomic_write_json(path, {"request_hash": request_hash, "result": dict(result)})

    @staticmethod
    def _payload_hash(value: object) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _append_audit(root: Path, value: Mapping[str, object]) -> None:
        root.mkdir(parents=True, exist_ok=True)
        with (root / "audit.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


__all__ = [
    "ProjectInitializationConflict", "ProjectInitializationError",
    "ProjectInitializationStore", "claim_objects", "validate_local_input_path",
]
