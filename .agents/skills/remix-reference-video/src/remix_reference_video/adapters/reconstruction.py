"""Materialization and reconstruction-stage orchestration adapters."""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from ..storage import read_json_object


class ReconstructionAdapter:
    def __init__(self, task_root: Path, asset_root: Path) -> None:
        self.task_root = Path(task_root).resolve(strict=True)
        self.asset_root = Path(asset_root).resolve(strict=True)

    def materialize_approved_broad(self, *, fragment_plan_path: Path) -> dict[str, object]:
        plan_path = self._task_file(fragment_plan_path, "fragment_plan.json")
        plan = read_json_object(plan_path)
        if plan.get("artifact_type") != "fragment_plan" or plan.get("lifecycle_status") != "approved":
            raise ValueError("approved fragment_plan is required")
        rows = plan.get("fragments")
        if not isinstance(rows, list) or not rows:
            raise ValueError("fragment plan has no fragments")
        prepared: list[tuple[dict[str, object], Path, str]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                raise ValueError("fragment plan row is invalid")
            fragment_id, relative = raw.get("fragment_id"), raw.get("source_path")
            if not isinstance(fragment_id, str) or not fragment_id:
                raise ValueError("fragment_id is required")
            if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
                raise ValueError(f"{fragment_id} source_path must be asset-relative")
            requested = self.asset_root / relative
            if requested.is_symlink():
                raise ValueError(f"{fragment_id} source must not be a symlink")
            source = requested.resolve(strict=True)
            if self.asset_root not in source.parents or not source.is_file():
                raise ValueError(f"{fragment_id} source escapes asset root")
            digest = self._sha256(source)
            if digest != raw.get("source_sha256"):
                raise ValueError(f"{fragment_id} source hash mismatch")
            prepared.append((raw, source, digest))
        manifest_rows: list[dict[str, object]] = []
        for row, source, digest in prepared:
            fragment_id = str(row["fragment_id"])
            destination = self.task_root / "material" / fragment_id / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if self._sha256(destination) != digest:
                    raise ValueError(f"immutable material differs for {fragment_id}")
            else:
                shutil.copy2(source, destination)
            material_hash = self._sha256(destination)
            manifest_rows.append(
                {
                    "fragment_id": fragment_id,
                    "source_path": source.relative_to(self.asset_root).as_posix(),
                    "source_sha256": digest,
                    "approved_broad_range": row.get("approved_broad_range"),
                    "copy_mode": "full_source_copy",
                    "material_path": destination.relative_to(self.task_root).as_posix(),
                    "material_sha256": material_hash,
                }
            )
        return {
            "artifact_type": "material_manifest",
            "schema_id": "urn:capcut:remix-reference-video:artifact:material-manifest",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "fragment_plan_sha256": self._sha256(plan_path),
            "fragments": manifest_rows,
        }

    @staticmethod
    def proxy_profile(task_config: Mapping[str, object]) -> dict[str, int]:
        profile = task_config.get("proxy_profile", "default")
        if profile == "default":
            return {"width": 540, "height": 960, "fps": 30}
        if profile == "review_high":
            return {"width": 720, "height": 1280, "fps": 30}
        raise ValueError("unsupported proxy profile")

    def render_proxy(
        self,
        *,
        timeline: Mapping[str, object],
        gate_status: Mapping[str, object],
        task_config: Mapping[str, object],
        renderer: Callable[..., Mapping[str, object]],
    ) -> Mapping[str, object]:
        if (
            gate_status.get("gate4_post_generation") != "approved"
            or gate_status.get("gate4") != "approved"
        ):
            raise ValueError("Gate 4 post approval is required before proxy render")
        if timeline.get("artifact_type") != "reconstruction_timeline":
            raise ValueError("reconstruction timeline is required")
        return renderer(timeline=timeline, profile=self.proxy_profile(task_config))

    @staticmethod
    def validate_proxy_boundaries(
        *,
        timeline: Mapping[str, object],
        observed_frame_times: Sequence[float],
        fps: int,
    ) -> dict[str, object]:
        rows = timeline.get("fragments")
        if not isinstance(rows, list) or fps <= 0:
            raise ValueError("timeline fragments and positive fps are required")
        tolerance = 1.0 / fps
        boundary_rows: list[dict[str, object]] = []
        for row in rows[:-1]:
            if not isinstance(row, Mapping) or not isinstance(
                row.get("timeline_end_seconds"), (int, float)
            ):
                raise ValueError("timeline boundary is invalid")
            boundary = float(row["timeline_end_seconds"])
            nearby = sorted(
                value for value in observed_frame_times if abs(float(value) - boundary) <= tolerance + 1e-9
            )
            boundary_rows.append(
                {
                    "boundary_seconds": boundary,
                    "observed_frame_times": nearby,
                    "status": "passed" if nearby else "failed",
                }
            )
        return {
            "artifact_type": "proxy_boundary_report",
            "status": "failed" if any(row["status"] == "failed" for row in boundary_rows) else "passed",
            "boundary_frames": boundary_rows,
        }

    def _task_file(self, path: Path, name: str) -> Path:
        requested = Path(path)
        if requested.name != name or requested.is_symlink():
            raise ValueError(f"input must be {name}")
        resolved = requested.resolve(strict=True)
        if self.task_root not in resolved.parents:
            raise ValueError(f"{name} escapes task root")
        return resolved

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
