"""Manifest for the shared incremental technical asset index."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..asset_index import ASSET_INDEX_IMPLEMENTATION_VERSION, AssetIndexer
from ..storage import StorageError
from . import content_fingerprint


class AssetIndexAdapter:
    execution_stage_id = "index-assets"
    implementation_version = ASSET_INDEX_IMPLEMENTATION_VERSION
    stop_gate = None

    def __init__(
        self,
        task_root: Path,
        asset_root: Path,
        shared_index_path: Path,
        *,
        probe: Callable[[Path, str], dict[str, object]] | None = None,
    ) -> None:
        self.task_root = Path(task_root).resolve(strict=True)
        requested_root = Path(asset_root)
        if requested_root.is_symlink():
            raise StorageError("asset root must not be a symlink")
        self.asset_root = requested_root.resolve(strict=True)
        self.shared_index_path = Path(shared_index_path).resolve(strict=False)
        self.probe = probe
        if (
            self.shared_index_path == self.asset_root
            or self.asset_root in self.shared_index_path.parents
        ):
            raise StorageError("shared index must remain outside asset root")

    def required_inputs(self) -> tuple[Path, ...]:
        return (self.asset_root,)

    def required_gates(self) -> tuple[str, ...]:
        return ()

    def declared_outputs(self) -> tuple[Path, ...]:
        return (self.shared_index_path,)

    def cache_fingerprint(self) -> str:
        return content_fingerprint(
            self.execution_stage_id,
            self.implementation_version,
            self.required_inputs(),
        )

    def execute(self, *, attempt_id: str) -> dict[str, object]:
        if not isinstance(attempt_id, str) or not attempt_id:
            raise StorageError("attempt_id is required")
        summary = AssetIndexer(
            self.shared_index_path,
            probe=self.probe,
            implementation_version=self.implementation_version,
        ).index(self.asset_root)
        return {"attempt_id": attempt_id, **summary.to_dict()}
