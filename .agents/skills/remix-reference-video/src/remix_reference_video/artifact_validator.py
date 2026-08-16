"""Read-only validation for Track B artifacts and delivery bundles."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .storage import StorageError, read_json_object

_ENVELOPE = {
    "schema_version": "1.0.0",
    "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
}
_GATE5_FILES = (
    "remix.mp4",
    "captions.srt",
    "final_validation_report.json",
    "render_report.json",
    "jianying_import_manifest.json",
)


@dataclass(frozen=True, slots=True)
class ValidationResult:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        if self.errors:
            return "failed"
        return "passed_with_warnings" if self.warnings else "passed"


class ArtifactValidator:
    def __init__(self, task_root: Path) -> None:
        self.root = Path(task_root).resolve(strict=True)
        if not self.root.is_dir():
            raise StorageError("task root must be a directory")

    def validate_artifact(
        self, path: Path, expected_type: str | None = None
    ) -> ValidationResult:
        errors: list[str] = []
        try:
            resolved = self._path(path, must_exist=True)
            value = read_json_object(resolved)
        except StorageError as error:
            return ValidationResult((str(error),))
        artifact_type = value.get("artifact_type")
        if not isinstance(artifact_type, str) or not artifact_type:
            errors.append("artifact_type is required")
        elif expected_type is not None and artifact_type != expected_type:
            errors.append(
                f"artifact_type must be {expected_type!r}, found {artifact_type!r}"
            )
        schema_id = value.get("schema_id")
        if not isinstance(schema_id, str) or not schema_id:
            errors.append("schema_id is required")
        for field, expected in _ENVELOPE.items():
            if value.get(field) != expected:
                errors.append(f"{field} must be {expected!r}")
        return ValidationResult(tuple(errors))

    def validate_hash(self, relative_path: str, expected_hash: str) -> ValidationResult:
        try:
            if not isinstance(relative_path, str) or Path(relative_path).is_absolute():
                raise StorageError("artifact path must be task-relative")
            path = self._path(self.root / relative_path, must_exist=True)
            if not self._is_sha256(expected_hash):
                raise StorageError("artifact SHA-256 is invalid")
            if self._sha256(path) != expected_hash:
                raise StorageError(f"artifact hash mismatch: {relative_path}")
        except StorageError as error:
            return ValidationResult((str(error),))
        return ValidationResult()

    def validate_timeline(
        self,
        timeline: Mapping[str, object],
        fragment_plan: Mapping[str, object],
    ) -> ValidationResult:
        errors: list[str] = []
        plan_rows = fragment_plan.get("fragments")
        timeline_rows = timeline.get("fragments")
        if not isinstance(plan_rows, list) or not isinstance(timeline_rows, list):
            return ValidationResult(("fragment plan and timeline fragments must be arrays",))
        broad: dict[str, tuple[float, float]] = {}
        for row in plan_rows:
            if not isinstance(row, Mapping) or not isinstance(row.get("fragment_id"), str):
                errors.append("fragment plan row is invalid")
                continue
            value = row.get("approved_broad_range")
            if not isinstance(value, Mapping):
                errors.append(f"{row.get('fragment_id')} has no approved broad range")
                continue
            start, end = value.get("start_seconds"), value.get("end_seconds")
            if start is None and end is None:
                continue
            if not self._range(start, end):
                errors.append(f"{row['fragment_id']} broad range is invalid")
                continue
            broad[str(row["fragment_id"])] = (float(start), float(end))
        for row in timeline_rows:
            if not isinstance(row, Mapping) or not isinstance(row.get("fragment_id"), str):
                errors.append("timeline row is invalid")
                continue
            fragment_id = str(row["fragment_id"])
            exact = (row.get("source_start_seconds"), row.get("source_end_seconds"))
            if fragment_id not in broad:
                if any(item is not None for item in exact):
                    errors.append(f"{fragment_id} has exact range without broad approval")
                continue
            if not self._range(*exact):
                errors.append(f"{fragment_id} exact range is invalid")
                continue
            start, end = broad[fragment_id]
            if float(exact[0]) < start or float(exact[1]) > end:
                errors.append(f"{fragment_id} exact range exceeds broad approval")
        return ValidationResult(tuple(errors))

    def validate_gate5_bundle(
        self, artifacts: Mapping[str, object]
    ) -> ValidationResult:
        errors: list[str] = []
        for name in _GATE5_FILES:
            record = artifacts.get(name)
            if not isinstance(record, Mapping):
                errors.append(f"Gate 5 artifact is not registered: {name}")
                continue
            path = record.get("path")
            digest = record.get("sha256")
            if not isinstance(path, str):
                errors.append(f"Gate 5 artifact path is invalid: {name}")
                continue
            result = self.validate_hash(path, str(digest))
            errors.extend(result.errors)
        return ValidationResult(tuple(errors))

    def _path(self, path: Path, *, must_exist: bool) -> Path:
        requested = Path(path)
        if requested.is_symlink():
            raise StorageError(f"artifact path must not be a symlink: {requested}")
        try:
            resolved = requested.resolve(strict=must_exist)
        except OSError as error:
            raise StorageError(f"artifact is missing: {requested}") from error
        if resolved != self.root and self.root not in resolved.parents:
            raise StorageError("artifact path escapes task root")
        if must_exist and not resolved.is_file():
            raise StorageError("artifact path must be a regular file")
        return resolved

    @staticmethod
    def _range(start: object, end: object) -> bool:
        if isinstance(start, bool) or isinstance(end, bool):
            return False
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            return False
        return 0 <= float(start) < float(end)

    @staticmethod
    def _is_sha256(value: object) -> bool:
        return isinstance(value, str) and len(value) == 64 and all(
            character in "0123456789abcdef" for character in value
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
