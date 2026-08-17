"""Full-shape validation for Track-B measurement artifacts and CLI inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, RefResolver
except ImportError:  # pragma: no cover - development environments may omit optional deps
    Draft202012Validator = None  # type: ignore[assignment]
    RefResolver = None  # type: ignore[assignment]


class SnapshotSchemaError(ValueError):
    pass


class SnapshotSchemaValidator:
    def __init__(self, schemas_root: Path | None = None) -> None:
        self.root = (schemas_root or Path(__file__).resolve().parents[2] / "schemas").resolve(strict=True)

    def validate(self, value: Any, schema_name: str) -> tuple[str, ...]:
        schema_path = self._schema_path(schema_name)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if Draft202012Validator is not None:
            validator = Draft202012Validator(schema)
            return tuple(self._format_error(error) for error in sorted(validator.iter_errors(value), key=lambda item: list(item.path)))
        return self._fallback_validate(value, schema_name)

    def assert_valid(self, value: Any, schema_name: str) -> None:
        errors = self.validate(value, schema_name)
        if errors:
            raise SnapshotSchemaError("; ".join(errors))

    def _schema_path(self, schema_name: str) -> Path:
        requested = Path(schema_name)
        if requested.is_absolute() or ".." in requested.parts or requested.is_symlink():
            raise SnapshotSchemaError("schema path escapes schema root")
        path = (self.root / requested).resolve(strict=True)
        if path != self.root and self.root not in path.parents:
            raise SnapshotSchemaError("schema path escapes schema root")
        if not path.is_file():
            raise SnapshotSchemaError(f"schema is missing: {schema_name}")
        return path

    @staticmethod
    def _format_error(error: Any) -> str:
        pointer = "".join(f"/{part}" for part in error.absolute_path)
        return f"{pointer or '/'}: {error.message}"

    @staticmethod
    def _fallback_validate(value: Any, schema_name: str) -> tuple[str, ...]:
        if not isinstance(value, dict):
            return ("/: value must be an object",)
        required = {
            "phase6-score-snapshot.schema.json": ("artifact_type", "schema_id", "snapshot_id", "run_id", "measurement_status", "framework_stages"),
            "process-assessment.schema.json": ("artifact_type", "schema_id", "run_id", "measurement_status", "approvals", "metrics"),
        }.get(schema_name, ())
        return tuple(f"/{field}: is a required property" for field in required if field not in value)
