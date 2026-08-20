"""Local, non-authoritative project drafts for Stage 0 initialization."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import unicodedata
import uuid
from argparse import Namespace
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator, Mapping

from .asset_index import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from .gb_frozen_case import CREATIVE_CONTRACT_VERSION
from .run_registry import RunRegistry
from .runtime_resolver import RuntimeResolver, RuntimeUnavailable
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
        with self._lock():
            return self._reserve_task_root_unlocked(project_id, task_name, date)

    def run_stage0(
        self,
        project_id: str,
        *,
        request_id: str,
        idempotency_key: str,
        actor: str,
        probe: object | None = None,
        cancel_check: object | None = None,
    ) -> dict[str, object]:
        from .asset_index import FFprobeAdapter

        draft = self.read_draft(project_id)
        key = _normalize_text(idempotency_key, "idempotency_key")
        request_hash = self._payload_hash({"action": "stage0", "project_id": project_id, "revision": draft["draft_revision"]})
        with self._lock():
            replay = self._read_idempotency(key)
            if replay is not None:
                if replay.get("request_hash") != request_hash:
                    raise ProjectInitializationConflict("idempotency key was used with different input")
                return dict(replay["result"])
        project_root = self._project_root(project_id)
        staging = project_root / ".staging" / _normalize_text(request_id, "request_id")
        if staging.exists():
            shutil.rmtree(staging)
        candidate = staging / "stage0-candidate"
        candidate.mkdir(parents=True)
        report_path = project_root / "stage0_report.json"
        try:
            if callable(cancel_check) and bool(cancel_check()):
                report = self._stage0_report(draft, "cancelled", {}, [], ["重新执行 Stage 0"])
                atomic_write_json(report_path, report)
                result = {**report, "report_sha256": self._sha256(report_path)}
                self._record_project_state(project_root, "draft")
                with self._lock():
                    self._write_idempotency(key, request_hash, result)
                return result
            reference = validate_local_input_path(Path(str(draft["reference_path"])), kind="reference")
            assets = validate_local_input_path(Path(str(draft["asset_root"])), kind="asset_root")
            copied_reference = candidate / f"reference-{datetime.now().date().isoformat()}{reference.suffix.lower()}"
            shutil.copy2(reference, copied_reference)
            profiles: list[dict[str, object]] = []
            risks: list[dict[str, object]] = []
            probe_media = probe if callable(probe) else FFprobeAdapter()
            snapshot: dict[str, str] = {}
            for path in sorted(assets.rglob("*")):
                relative = path.relative_to(assets).as_posix()
                if path.is_symlink():
                    risks.append({"code": "symlink", "path": relative})
                    continue
                if not path.is_file():
                    continue
                suffix = path.suffix.lower()
                media_type = "image" if suffix in IMAGE_EXTENSIONS else ("video" if suffix in VIDEO_EXTENSIONS else None)
                if media_type is None:
                    continue
                digest = self._sha256(path)
                try:
                    technical = dict(probe_media(path, media_type))
                except Exception as error:
                    risks.append({"code": "scan_error", "path": relative, "detail": str(error)})
                    continue
                snapshot[relative] = digest
                profiles.append({
                    "asset_id": "asset-" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16],
                    "source_path": relative, "sha256": digest, "media_type": media_type,
                    **{name: technical[name] for name in (
                        "codec_name", "width", "height", "frame_rate", "duration_seconds",
                        "has_audio", "format_name",
                    ) if name in technical},
                })
            status = "blocked" if risks or not profiles else "ready"
            brief = self._canonical_brief(draft, object_claims=False)
            atomic_write_json(candidate / "project_brief.json", brief)
            self._write_yaml(candidate / "project_brief.yaml", brief)
            atomic_write_json(candidate / "asset_profiles.json", {
                **_ENVELOPE, "artifact_type": "asset_profiles",
                "schema_id": "urn:capcut:remix-reference-video:artifact:asset-profiles",
                "asset_profiles": profiles,
            })
            atomic_write_json(candidate / "stage0_input_snapshot.json", {
                "reference_sha256": self._sha256(reference), "asset_snapshot": snapshot,
                "draft_revision": draft["draft_revision"],
            })
            report = self._stage0_report(
                draft, status,
                {"reference": self._sha256(reference), **{f"asset:{name}": digest for name, digest in snapshot.items()}},
                risks, ["处理风险后重新执行 Stage 0"] if risks else [],
                asset_summary={"supported_files": len(profiles), "images": sum(row["media_type"] == "image" for row in profiles), "videos": sum(row["media_type"] == "video" for row in profiles)},
            )
            atomic_write_json(report_path, report)
            published = project_root / "stage0-candidate"
            if published.exists():
                shutil.rmtree(published)
            if status == "ready":
                os.replace(candidate, published)
                self._record_project_state(project_root, "stage0_awaiting_confirmation")
            else:
                self._record_project_state(project_root, "blocked")
            result = {**report, "report_sha256": self._sha256(report_path)}
            with self._lock():
                self._append_audit(project_root, {
                    "action": "stage0.completed", "actor": _normalize_text(actor, "actor"),
                    "request_id": request_id, "idempotency_key": key, "result": status, "recorded_at": _now(),
                })
                self._write_idempotency(key, request_hash, result)
            return result
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def freeze(
        self,
        project_id: str,
        *,
        expected_draft_revision: int,
        expected_report_sha256: str,
        actor: str,
        request_id: str,
        idempotency_key: str,
        date: str,
    ) -> dict[str, object]:
        project_root = self._project_root(project_id)
        draft = self.read_draft(project_id)
        if draft.get("draft_revision") != expected_draft_revision:
            raise ProjectInitializationConflict("draft revision conflict")
        report_path = project_root / "stage0_report.json"
        if self._sha256(report_path) != expected_report_sha256:
            raise ProjectInitializationConflict("Stage 0 report hash conflict")
        report = read_json_object(report_path)
        if report.get("status") != "ready":
            raise ProjectInitializationConflict("Stage 0 is not ready to freeze")
        candidate = project_root / "stage0-candidate"
        snapshot = read_json_object(candidate / "stage0_input_snapshot.json")
        reference_source = validate_local_input_path(Path(str(draft["reference_path"])), kind="reference")
        if self._sha256(reference_source) != snapshot.get("reference_sha256"):
            raise ProjectInitializationConflict("input changed after Stage 0")
        asset_root = validate_local_input_path(Path(str(draft["asset_root"])), kind="asset_root")
        for relative, digest in dict(snapshot.get("asset_snapshot", {})).items():
            source = asset_root / str(relative)
            if source.is_symlink() or not source.is_file() or self._sha256(source) != digest:
                raise ProjectInitializationConflict("input changed after Stage 0")
        key = _normalize_text(idempotency_key, "idempotency_key")
        request_hash = self._payload_hash({"action": "freeze", "project_id": project_id, "report": expected_report_sha256})
        with self._lock():
            replay = self._read_idempotency(key)
            if replay is not None:
                if replay.get("request_hash") != request_hash:
                    raise ProjectInitializationConflict("idempotency key was used with different input")
                return dict(replay["result"])
            task_root = self._reserve_task_root_unlocked(project_id, str(draft["task_name"]), date)
            frozen = task_root / "frozen-input"
            if frozen.exists():
                raise ProjectInitializationConflict("frozen input already exists")
            shutil.copytree(candidate, frozen, ignore=shutil.ignore_patterns("stage0_input_snapshot.json"))
            brief = self._canonical_brief(draft, object_claims=True)
            atomic_write_json(frozen / "project_brief.json", brief)
            self._write_yaml(frozen / "project_brief.yaml", brief)
            profiles = frozen / "asset_profiles.json"
            reference = next(frozen.glob("reference-*"))
            marker = {
                **_ENVELOPE, "artifact_type": "g_b_frozen_input_snapshot",
                "schema_id": "urn:capcut:remix-reference-video:artifact:g-b-frozen-input-snapshot",
                "reference_sha256": self._sha256(reference), "brief_sha256": self._sha256(frozen / "project_brief.json"),
                "asset_profiles_sha256": self._sha256(profiles), "asset_snapshot": dict(snapshot["asset_snapshot"]),
                "asset_snapshot_contract_version": "relative_path_v1", "creative_contract_version": CREATIVE_CONTRACT_VERSION,
                "approval_records": [],
            }
            atomic_write_json(frozen / "g_b_frozen_input_snapshot.json", marker)
            result = {"project_id": project_id, "status": "frozen_waiting_gate1", "task_root": str(task_root), "frozen_root": str(frozen)}
            self._record_project_state(project_root, "frozen_waiting_gate1", task_root=task_root)
            self._append_audit(project_root, {"action": "project.frozen", "actor": actor, "request_id": request_id, "idempotency_key": key, "recorded_at": _now()})
            self._write_idempotency(key, request_hash, result)
            return result

    def start_cold(
        self,
        project_id: str,
        *, actor: str, request_id: str, idempotency_key: str,
        runtime_resolver: RuntimeResolver | None = None,
        pair_runner: object | None = None,
    ) -> dict[str, object]:
        project_root = self._project_root(project_id)
        state = read_json_object(project_root / "project_state.json")
        task_root = Path(str(state.get("task_root", "")))
        if state.get("lifecycle_status") != "frozen_waiting_gate1" or not task_root.is_dir():
            raise ProjectInitializationConflict("project is not waiting to start Gate 1")
        try:
            runtime = (runtime_resolver or RuntimeResolver(self.workspace)).resolve()
        except RuntimeUnavailable as error:
            return {"project_id": project_id, "status": "runtime_unavailable", "detail": str(error)}
        from .cli import run_gb_pair

        args = Namespace(
            frozen_root=task_root / "frozen-input", asset_root=Path(str(self.read_draft(project_id)["asset_root"])),
            cold_task_dir=task_root / "cold", hot_task_dir=task_root / "hot", pair_root=task_root,
            doubao_client=runtime.doubao_client_script, python_executable=str(runtime.python_executable),
            decision_dir=None, actor=actor, creative_contract="v1", resume_existing=False,
        )
        runner = pair_runner if callable(pair_runner) else run_gb_pair
        result = dict(runner(args))
        cold_root = task_root / "cold"
        registration = RunRegistry(self.workspace).ensure_registered(cold_root)
        response = {"project_id": project_id, "status": "cold_running_or_awaiting_review", "run_id": registration["run_id"], "task_root": str(cold_root), "pair_status": result.get("status")}
        self._record_project_state(project_root, "cold_running_or_awaiting_review", task_root=task_root, run_id=str(registration["run_id"]))
        self._append_audit(project_root, {"action": "cold.started", "actor": actor, "request_id": request_id, "idempotency_key": idempotency_key, "recorded_at": _now()})
        return response

    @staticmethod
    def _stage0_report(
        draft: Mapping[str, object], status: str, input_hashes: Mapping[str, str],
        risks: list[dict[str, object]], suggested_actions: list[str],
        *, asset_summary: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            **_ENVELOPE, "artifact_type": "stage0_report",
            "schema_id": "urn:capcut:remix-reference-video:artifact:stage0-report",
            "project_id": draft["project_id"], "draft_revision": draft["draft_revision"],
            "status": status, "input_hashes": dict(input_hashes),
            "checks": [], "asset_summary": dict(asset_summary or {}), "risks": risks,
            "missing_fields": [], "suggested_actions": suggested_actions,
        }

    @staticmethod
    def _canonical_brief(draft: Mapping[str, object], *, object_claims: bool) -> dict[str, object]:
        approved = claim_objects(draft["approved_claims"]) if object_claims else list(draft["approved_claims"])
        forbidden = claim_objects(draft["forbidden_claims"]) if object_claims else list(draft["forbidden_claims"])
        return {
            **_ENVELOPE, "artifact_type": "project_brief",
            "schema_id": "urn:capcut:remix-reference-video:artifact:project-brief",
            "product": {"name": draft["product_name"], "audience": draft["audience"]},
            "target": {"platform": draft["platform"], **dict(draft["output"])},
            "approved_claims": approved, "forbidden_claims": forbidden, "approved_fallbacks": [],
            "voice": dict(draft["voice"]), "maximum_narration_chars_per_second": 5,
            "duration_envelope": {"minimum_seconds": 1, "maximum_seconds": 60, "strength": "soft"},
        }

    @staticmethod
    def _write_yaml(path: Path, value: Mapping[str, object]) -> None:
        try:
            import yaml
            payload = yaml.safe_dump(dict(value), allow_unicode=True, sort_keys=True)
        except ImportError:
            payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        path.write_text(payload, encoding="utf-8")

    @staticmethod
    def _sha256(path: Path) -> str:
        with Path(path).open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    @staticmethod
    def _record_project_state(root: Path, lifecycle: str, **extra: object) -> None:
        path = root / "project_state.json"
        current = read_json_object(path) if path.is_file() else {}
        serializable = {key: str(value) if isinstance(value, Path) else value for key, value in extra.items()}
        atomic_write_json(path, {**current, "lifecycle_status": lifecycle, "updated_at": _now(), **serializable})

    def _reserve_task_root_unlocked(self, project_id: str, task_name: str, date: str) -> Path:
        target = self.workspace / "work" / f"{date}-{task_name}"
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
