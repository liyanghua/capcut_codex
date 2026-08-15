"""Manifest for deterministic reference-video splitting."""

from __future__ import annotations

from pathlib import Path

from ..storage import StorageError
from . import content_fingerprint


class ReferenceSplitAdapter:
    execution_stage_id = "split-reference"
    implementation_version = "reference-split-v1"
    stop_gate = "gate1"

    def __init__(self, task_root: Path, reference_path: Path) -> None:
        self.task_root = Path(task_root).resolve(strict=True)
        requested = Path(reference_path)
        if requested.is_symlink():
            raise StorageError("reference input must not be a symlink")
        self.reference_path = requested.resolve(strict=True)
        if self.task_root not in self.reference_path.parents:
            raise StorageError("reference input must be inside task root")

    def required_inputs(self) -> tuple[Path, ...]:
        return (self.reference_path,)

    def required_gates(self) -> tuple[str, ...]:
        return ()

    def declared_outputs(self) -> tuple[Path, ...]:
        return (
            self.task_root / "recipe.json",
            self.task_root / "video_clips",
            self.task_root / "review_contact_sheet.jpg",
            self.task_root / "gate_review_packages/gate1.json",
        )

    def cache_fingerprint(self) -> str:
        return content_fingerprint(
            self.execution_stage_id,
            self.implementation_version,
            self.required_inputs(),
        )
