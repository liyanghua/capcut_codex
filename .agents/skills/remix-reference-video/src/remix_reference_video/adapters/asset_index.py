"""Manifest for the shared incremental technical asset index."""

from __future__ import annotations

from pathlib import Path

from ..storage import StorageError
from . import content_fingerprint


class AssetIndexAdapter:
    execution_stage_id = "index-assets"
    implementation_version = "asset-index-v2"
    stop_gate = None

    def __init__(
        self, task_root: Path, asset_root: Path, shared_index_path: Path
    ) -> None:
        self.task_root = Path(task_root).resolve(strict=True)
        requested_root = Path(asset_root)
        if requested_root.is_symlink():
            raise StorageError("asset root must not be a symlink")
        self.asset_root = requested_root.resolve(strict=True)
        self.shared_index_path = Path(shared_index_path).resolve(strict=False)
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
