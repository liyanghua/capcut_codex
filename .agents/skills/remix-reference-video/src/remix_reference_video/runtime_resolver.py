"""Resolve trusted local runtime dependencies outside project inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .storage import StorageError, read_json_object


class RuntimeUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedRuntime:
    python_executable: Path
    doubao_client_script: Path


class RuntimeResolver:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace = Path(workspace_root).resolve(strict=True)
        self.config_path = self.workspace / "workbench" / "runtime_config.json"

    def resolve(self) -> ResolvedRuntime:
        try:
            value = read_json_object(self.config_path)
        except (OSError, StorageError) as error:
            raise RuntimeUnavailable("trusted runtime configuration is missing") from error
        return ResolvedRuntime(
            python_executable=self._executable(value.get("python_executable"), "python executable"),
            doubao_client_script=self._file(value.get("doubao_client_script"), "Doubao client"),
        )

    @staticmethod
    def _file(value: object, label: str, *, allow_symlink: bool = False) -> Path:
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise RuntimeUnavailable(f"{label} path must be absolute")
        requested = Path(value)
        if requested.is_symlink() and not allow_symlink:
            raise RuntimeUnavailable(f"{label} path must not be a symlink")
        try:
            resolved = requested.resolve(strict=True)
        except OSError as error:
            raise RuntimeUnavailable(f"{label} is unavailable") from error
        if not resolved.is_file():
            raise RuntimeUnavailable(f"{label} must be a regular file")
        return resolved

    @classmethod
    def _executable(cls, value: object, label: str) -> Path:
        resolved = cls._file(value, label, allow_symlink=True)
        if not resolved.stat().st_mode & 0o111:
            raise RuntimeUnavailable(f"{label} is not executable")
        return resolved


__all__ = ["ResolvedRuntime", "RuntimeResolver", "RuntimeUnavailable"]
