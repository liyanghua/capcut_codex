"""Validation for task-local stage handoff contracts.

Stage inputs are an auditable handoff between an operator/agent and an adapter.
They are deliberately not approval records; ``pipeline_state.json`` remains the
only source of truth for Gate decisions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from .storage import StorageError, read_json_object


_ENVELOPE = {
    "schema_version": "1.0.0",
    "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
}
_LIFECYCLE = frozenset({"draft", "awaiting_user", "stale", "consumed"})
_RESERVED_APPROVAL_KEYS = frozenset(
    {
        "gate_status",
        "approval",
        "approvals",
        "approval_status",
        "approved",
        "review_package_hash",
        "approval_timestamp",
    }
)


@dataclass(frozen=True, slots=True)
class StageInputValidationResult:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors


class StageInputValidator:
    """Validate stage handoffs without changing task state or files."""

    def __init__(self, task_root: Path) -> None:
        self.root = Path(task_root).resolve(strict=True)
        if not self.root.is_dir():
            raise StorageError("task root must be a directory")

    def validate(
        self,
        path: Path,
        *,
        expected_stage_id: str | None = None,
        expected_input_hashes: Mapping[str, str] | None = None,
    ) -> StageInputValidationResult:
        errors: list[str] = []
        try:
            resolved = self._safe_file(path)
            value = read_json_object(resolved)
        except (StorageError, OSError, json.JSONDecodeError) as error:
            return StageInputValidationResult((str(error),))

        for field, expected in _ENVELOPE.items():
            if value.get(field) != expected:
                errors.append(f"{field} must be {expected!r}")
        if value.get("artifact_type") != "stage_input":
            errors.append("artifact_type must be 'stage_input'")
        schema_id = value.get("schema_id")
        if schema_id != "urn:capcut:remix-reference-video:artifact:stage-input":
            errors.append("schema_id is invalid for stage_input")

        stage_id = value.get("stage_id")
        if not isinstance(stage_id, str) or not stage_id or Path(stage_id).name != stage_id:
            errors.append("stage_id must be a nonempty stage identifier")
        elif expected_stage_id is not None and stage_id != expected_stage_id:
            errors.append(f"stage_id must be {expected_stage_id!r}")
        producer = value.get("producer")
        if not isinstance(producer, (str, Mapping)) or not producer:
            errors.append("producer must be a nonempty string or object")
        created_at = value.get("created_at")
        if not isinstance(created_at, str) or not created_at:
            errors.append("created_at must be an ISO-8601 timestamp")
        else:
            try:
                datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                errors.append("created_at must be an ISO-8601 timestamp")
        lifecycle = value.get("lifecycle_status")
        if lifecycle not in _LIFECYCLE:
            errors.append("lifecycle_status must be draft, awaiting_user, stale, or consumed")

        hashes = value.get("input_hashes")
        if not isinstance(hashes, Mapping):
            errors.append("input_hashes must be an object")
            hashes = {}
        for relative, digest in hashes.items():
            if not isinstance(relative, str):
                errors.append("input_hashes paths must be strings")
                continue
            try:
                input_path = self._safe_relative_file(relative)
                if not self._is_sha256(digest):
                    raise StorageError(f"input hash is invalid: {relative}")
                actual = self._sha256(input_path)
                if actual != digest:
                    raise StorageError(f"input hash mismatch: {relative}")
            except StorageError as error:
                errors.append(str(error))
        if expected_input_hashes is not None and dict(hashes) != dict(expected_input_hashes):
            errors.append("input_hashes do not match the adapter's declared inputs")

        payload = value.get("payload")
        if not isinstance(payload, Mapping):
            errors.append("payload must be an object")
        if self._contains_reserved_key(value):
            errors.append("stage_input must not contain Gate approval fields")
        return StageInputValidationResult(tuple(errors))

    def validate_all(self) -> StageInputValidationResult:
        directory = self.root / "stage_inputs"
        if not directory.exists():
            return StageInputValidationResult()
        if directory.is_symlink() or not directory.is_dir():
            return StageInputValidationResult(("stage_inputs must be a regular directory",))
        errors: list[str] = []
        for path in sorted(directory.glob("*.json")):
            result = self.validate(path, expected_stage_id=path.stem)
            errors.extend(f"{path.relative_to(self.root)}: {error}" for error in result.errors)
        return StageInputValidationResult(tuple(errors))

    def _safe_file(self, path: Path) -> Path:
        requested = Path(path)
        if requested.is_symlink():
            raise StorageError(f"stage input must not be a symlink: {requested}")
        resolved = requested.resolve(strict=True)
        if resolved.parent != self.root / "stage_inputs":
            raise StorageError("stage input must be directly under stage_inputs")
        if not resolved.is_file():
            raise StorageError("stage input path must be a regular file")
        return resolved

    def _safe_relative_file(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
            raise StorageError(f"input path must be task-relative: {relative}")
        resolved = (self.root / candidate).resolve(strict=True)
        if resolved == self.root or self.root not in resolved.parents:
            raise StorageError(f"input path escapes task root: {relative}")
        current = self.root
        for part in candidate.parts:
            current = current / part
            if current.is_symlink():
                raise StorageError(f"input path must not use a symlink: {relative}")
        if not resolved.is_file():
            raise StorageError(f"input path must be a regular file: {relative}")
        return resolved

    @staticmethod
    def _contains_reserved_key(value: object) -> bool:
        if isinstance(value, Mapping):
            return any(
                key in _RESERVED_APPROVAL_KEYS or StageInputValidator._contains_reserved_key(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(StageInputValidator._contains_reserved_key(item) for item in value)
        return False

    @staticmethod
    def _is_sha256(value: object) -> bool:
        return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()


def stage_input_hashes(task_root: Path, relative_paths: list[str]) -> dict[str, str]:
    """Build canonical task-relative input hashes for an adapter handoff."""

    validator = StageInputValidator(task_root)
    return {relative: validator._sha256(validator._safe_relative_file(relative)) for relative in relative_paths}


__all__ = ["StageInputValidationResult", "StageInputValidator", "stage_input_hashes"]
