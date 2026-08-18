"""Containment and identity checks for media referenced by the read-only workspace."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


class WorkspaceMediaError(ValueError):
    """Raised when a workspace media reference is not safe or current."""


class WorkspaceMediaAuthorizer:
    """Authorize only paths explicitly emitted by the current workspace view."""

    def __init__(self, workspace_root: Path) -> None:
        root = Path(workspace_root)
        if root.is_symlink():
            raise WorkspaceMediaError("workspace root must not be a symlink")
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise WorkspaceMediaError("workspace root must be a directory")

    def authorize(
        self,
        projection: Mapping[str, Any],
        relative_path: str,
        *,
        run_id: str | None = None,
        state_revision: int | None = None,
        package_revision: int | str | None = None,
    ) -> str:
        if not isinstance(projection, Mapping):
            raise WorkspaceMediaError("workspace projection is required")
        expected_run = projection.get("run_id")
        if run_id is not None and run_id != expected_run:
            raise WorkspaceMediaError("workspace run identity is wrong")
        expected_revision = projection.get("state_revision")
        if state_revision is not None and state_revision != expected_revision:
            raise WorkspaceMediaError("workspace state revision is stale")
        expected_package = projection.get("package_revision", expected_revision)
        if package_revision is not None and package_revision != expected_package:
            raise WorkspaceMediaError("workspace package revision is stale")
        if not isinstance(relative_path, str) or not relative_path or Path(relative_path).is_absolute():
            raise WorkspaceMediaError("media path must be relative")
        allowlist = projection.get("media_allowlist")
        if not isinstance(allowlist, list) or relative_path not in allowlist:
            raise WorkspaceMediaError("media path was not emitted by this workspace projection")
        candidate = self.root / Path(relative_path)
        if candidate.is_symlink():
            raise WorkspaceMediaError("media path must not be a symlink")
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as error:
            raise WorkspaceMediaError("media path is absent") from error
        if self.root not in resolved.parents or not resolved.is_file():
            raise WorkspaceMediaError("media path escapes workspace root")
        return resolved.relative_to(self.root).as_posix()

    def authorize_path(
        self,
        relative_path: str,
        projection: Mapping[str, Any],
        **kwargs: Any,
    ) -> str:
        """Compatibility spelling for media endpoint callers."""

        return self.authorize(projection, relative_path, **kwargs)
