"""Deterministic visual layout and readability report builder (visual_layout_policy_v1)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .media_layout import LAYOUT_POLICY_VERSION, PRODUCTION_CANVAS, compute_layout
from .storage import StorageError, read_json_object


class VisualLayoutError(ValueError):
    """Raised when layout report inputs are invalid."""


class VisualLayoutBuilder:
    implementation_version = "visual-layout-v1"

    def build(
        self,
        *,
        fragment_plan_path: Path,
        asset_profiles_path: Path,
        material_manifest_path: Path,
        canvas: tuple[int, int] = PRODUCTION_CANVAS,
    ) -> dict[str, Any]:
        paths = {
            "fragment_plan.json": self._canonical_path(fragment_plan_path, "fragment_plan.json"),
            "asset_profiles.json": self._canonical_path(asset_profiles_path, "asset_profiles.json"),
            "material_manifest.json": self._canonical_path(material_manifest_path, "material_manifest.json"),
        }
        plan = read_json_object(paths["fragment_plan.json"])
        profiles = read_json_object(paths["asset_profiles.json"])
        manifest = read_json_object(paths["material_manifest.json"])
        if plan.get("artifact_type") != "fragment_plan":
            raise VisualLayoutError("fragment_plan artifact is required")
        if profiles.get("artifact_type") != "asset_profiles":
            raise VisualLayoutError("asset_profiles artifact is required")
        if manifest.get("artifact_type") != "material_manifest":
            raise VisualLayoutError("material_manifest artifact is required")
        profile_by_asset = {
            str(row.get("asset_id")): row
            for row in profiles.get("asset_profiles", [])
            if isinstance(row, Mapping) and isinstance(row.get("asset_id"), str)
        }
        canvas_width, canvas_height = canvas
        fragments: list[dict[str, Any]] = []
        for raw in plan.get("fragments", []):
            if not isinstance(raw, Mapping):
                raise VisualLayoutError("fragment plan row must be an object")
            fragment_id = str(raw.get("fragment_id", ""))
            if not fragment_id:
                raise VisualLayoutError("fragment plan row needs fragment_id")
            media_type = str(raw.get("media_type", ""))
            overlay_policy = str(raw.get("overlay_policy", ""))
            profile = profile_by_asset.get(str(raw.get("asset_id", "")), {})
            source_width = profile.get("width")
            source_height = profile.get("height")
            source_width = source_width if isinstance(source_width, int) and source_width > 0 else None
            source_height = source_height if isinstance(source_height, int) and source_height > 0 else None
            overlay_detected = profile.get("overlay_detected") is True
            require_contain = media_type == "image" or overlay_policy == "retain_source_text"
            if require_contain:
                layout = compute_layout(
                    source_width=source_width,
                    source_height=source_height,
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                    overlay_detected=overlay_detected,
                    known_text_height_px=None,
                )
                policy_field = "contain"
            else:
                layout = self._legacy_crop_layout(
                    source_width=source_width, source_height=source_height,
                    canvas_width=canvas_width, canvas_height=canvas_height,
                )
                policy_field = "none"
            fragments.append(
                {
                    "fragment_id": fragment_id,
                    "source_width": source_width,
                    "source_height": source_height,
                    "content_rect": layout["content_rect"],
                    "scale_factor": layout["scale_factor"],
                    "crop_pixels": int(layout["crop_pixels"]),
                    "overlay_policy": policy_field,
                    "readability_status": layout["readability_status"],
                    "suggestion": str(layout["suggestion"]),
                }
            )
        blocked = [row["fragment_id"] for row in fragments if row["readability_status"] == "blocked"]
        manual = [row["fragment_id"] for row in fragments if row["readability_status"] == "manual_review"]
        status = "blocked" if blocked else ("manual_review" if manual else "passed")
        return {
            "artifact_type": "visual_layout_report",
            "schema_id": "urn:capcut:remix-reference-video:artifact:visual-layout-report",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "implementation_version": self.implementation_version,
            "lifecycle_status": "ready",
            "input_hashes": {name: self._sha256(path) for name, path in paths.items()},
            "status": status,
            "layout_policy_version": LAYOUT_POLICY_VERSION,
            "canvas": {"width": canvas_width, "height": canvas_height},
            "fragments": fragments,
            "blocked_fragment_ids": list(dict.fromkeys([*blocked, *manual])),
            "allowed_resolutions": ["replace_approved_candidate", "supply_higher_quality_media"],
        }

    @staticmethod
    def _legacy_crop_layout(
        *, source_width: int | None, source_height: int | None, canvas_width: int, canvas_height: int
    ) -> dict[str, Any]:
        if source_width is None or source_height is None:
            return {
                "content_rect": {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
                "scale_factor": 0.0,
                "crop_pixels": 0,
                "readability_status": "manual_review",
                "suggestion": "素材画像缺少可判定的尺寸信息，请补充高清素材或更换已批准候选。",
            }
        scale = max(canvas_width / source_width, canvas_height / source_height)
        scaled_width = source_width * scale
        scaled_height = source_height * scale
        crop_pixels = max(0.0, scaled_width * scaled_height - canvas_width * canvas_height)
        return {
            "content_rect": {"x": 0.0, "y": 0.0, "w": float(canvas_width), "h": float(canvas_height)},
            "scale_factor": round(scale, 4),
            "crop_pixels": round(crop_pixels),
            "readability_status": "passed",
            "suggestion": "已批准裁切策略（非 contain），不适用源文字保留要求。",
        }

    @staticmethod
    def _canonical_path(path: Path, expected_name: str) -> Path:
        requested = Path(path)
        if requested.name != expected_name:
            raise VisualLayoutError(f"input path must be {expected_name}")
        if requested.is_symlink():
            raise VisualLayoutError(f"{expected_name} must not be a symlink")
        return requested.resolve(strict=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
