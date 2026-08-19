from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.artifact_validator import ArtifactValidator
from remix_reference_video.media_layout import (
    LAYOUT_POLICY_VERSION,
    MAX_UPSCALE_FACTOR,
    MIN_TEXT_HEIGHT_PX,
    ImageLayoutPolicyError,
    compute_layout,
    contain_filter,
)
from remix_reference_video import media_layout
from remix_reference_video.snapshot_schema_validator import SnapshotSchemaValidator
from remix_reference_video.storage import atomic_write_json
from remix_reference_video.visual_layout import VisualLayoutBuilder, VisualLayoutError


class MediaLayoutPolicyTests(unittest.TestCase):
    def test_shared_render_filter_matches_review_and_final_policy(self) -> None:
        self.assertTrue(hasattr(media_layout, "render_filter_for_media"))
        render_filter = media_layout.render_filter_for_media
        image = render_filter(suffix=".jpg", overlay_policy=None, canvas_width=1080, canvas_height=1920)
        retained_video = render_filter(suffix=".mp4", overlay_policy="retain_source_text", canvas_width=1080, canvas_height=1920)
        plain_video = render_filter(suffix=".mp4", overlay_policy=None, canvas_width=1080, canvas_height=1920)
        self.assertIn("force_original_aspect_ratio=decrease", image)
        self.assertIn("force_original_aspect_ratio=decrease", retained_video)
        self.assertIn("force_original_aspect_ratio=increase", plain_video)
        self.assertIn("crop=1080:1920", plain_video)

    def test_contain_layout_never_crops_and_centers(self) -> None:
        layout = compute_layout(source_width=2560, source_height=1440, canvas_width=1080, canvas_height=1920)
        self.assertEqual(layout["crop_pixels"], 0)
        self.assertEqual(layout["overlay_policy"], "contain")
        self.assertEqual(layout["readability_status"], "passed")
        rect = layout["content_rect"]
        self.assertAlmostEqual(rect["w"], 1080.0)
        self.assertAlmostEqual(rect["h"], 607.5)
        self.assertAlmostEqual(rect["y"], 656.25)

    def test_upscale_over_limit_blocks(self) -> None:
        layout = compute_layout(source_width=200, source_height=400, canvas_width=1080, canvas_height=1920)
        self.assertEqual(layout["readability_status"], "blocked")
        self.assertGreater(layout["scale_factor"], MAX_UPSCALE_FACTOR)

    def test_overlay_without_text_region_is_manual_review(self) -> None:
        layout = compute_layout(source_width=1080, source_height=1920, canvas_width=1080, canvas_height=1920, overlay_detected=True)
        self.assertEqual(layout["readability_status"], "manual_review")

    def test_overlay_with_small_text_region_blocks(self) -> None:
        layout = compute_layout(
            source_width=1000, source_height=2000, canvas_width=1080, canvas_height=1920,
            overlay_detected=True, known_text_height_px=10.0,
        )
        self.assertEqual(layout["readability_status"], "blocked")
        self.assertLess(10.0 * layout["scale_factor"], MIN_TEXT_HEIGHT_PX)

    def test_missing_source_dimensions_are_manual_review(self) -> None:
        layout = compute_layout(source_width=None, source_height=None, canvas_width=1080, canvas_height=1920)
        self.assertEqual(layout["readability_status"], "manual_review")

    def test_invalid_canvas_is_rejected(self) -> None:
        with self.assertRaises(ImageLayoutPolicyError):
            compute_layout(source_width=100, source_height=100, canvas_width=0, canvas_height=1920)
        with self.assertRaises(ImageLayoutPolicyError):
            contain_filter(canvas_width=0, canvas_height=1920)

    def test_contain_filter_scales_down_and_pads(self) -> None:
        filter_chain = contain_filter(canvas_width=1080, canvas_height=1920)
        self.assertIn("force_original_aspect_ratio=decrease", filter_chain)
        self.assertIn("pad=1080:1920", filter_chain)
        self.assertNotIn("crop", filter_chain)


class VisualLayoutBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.builder = VisualLayoutBuilder()

    def write(self, *, plan_fragments, profiles, overlay_policy="no_action", media_type="video"):
        atomic_write_json(
            self.root / "fragment_plan.json",
            {
                "artifact_type": "fragment_plan",
                "fragments": [
                    dict(row, overlay_policy=overlay_policy, media_type=media_type)
                    for row in plan_fragments
                ],
            },
        )
        atomic_write_json(
            self.root / "asset_profiles.json",
            {"artifact_type": "asset_profiles", "asset_profiles": profiles},
        )
        atomic_write_json(
            self.root / "material_manifest.json",
            {
                "artifact_type": "material_manifest",
                "fragments": [
                    {"fragment_id": row["fragment_id"], "material_path": "material/x"}
                    for row in plan_fragments
                ],
            },
        )

    def build(self):
        return self.builder.build(
            fragment_plan_path=self.root / "fragment_plan.json",
            asset_profiles_path=self.root / "asset_profiles.json",
            material_manifest_path=self.root / "material_manifest.json",
        )

    def test_image_fragment_uses_contain_and_passes(self) -> None:
        self.write(
            plan_fragments=[{"fragment_id": "fragment01", "asset_id": "asset-1"}],
            profiles=[{"asset_id": "asset-1", "width": 2160, "height": 3840, "overlay_detected": False}],
            media_type="image",
        )
        report = self.build()
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["layout_policy_version"], LAYOUT_POLICY_VERSION)
        row = report["fragments"][0]
        self.assertEqual(row["overlay_policy"], "contain")
        self.assertEqual(row["crop_pixels"], 0)
        self.assertEqual(row["readability_status"], "passed")
        SnapshotSchemaValidator().assert_valid(report, "visual-layout-report.schema.json")
        path = self.root / "visual_layout_report.json"
        atomic_write_json(path, report)
        self.assertTrue(ArtifactValidator(self.root).validate_quality_report(path).valid)

    def test_overlay_retained_video_requires_contain_and_surfaces_manual_review(self) -> None:
        self.write(
            plan_fragments=[{"fragment_id": "fragment01", "asset_id": "asset-1"}],
            profiles=[{"asset_id": "asset-1", "width": 1440, "height": 2560, "overlay_detected": True}],
            overlay_policy="retain_source_text",
        )
        report = self.build()
        self.assertEqual(report["status"], "manual_review")
        self.assertEqual(report["fragments"][0]["overlay_policy"], "contain")
        self.assertEqual(report["fragments"][0]["readability_status"], "manual_review")

    def test_video_without_overlay_keeps_legacy_crop_path(self) -> None:
        self.write(
            plan_fragments=[{"fragment_id": "fragment01", "asset_id": "asset-1"}],
            profiles=[{"asset_id": "asset-1", "width": 2560, "height": 1440, "overlay_detected": False}],
            overlay_policy="no_action",
        )
        report = self.build()
        self.assertEqual(report["status"], "passed")
        row = report["fragments"][0]
        self.assertEqual(row["overlay_policy"], "none")
        self.assertGreater(row["crop_pixels"], 0)

    def test_low_resolution_image_blocks_report(self) -> None:
        self.write(
            plan_fragments=[{"fragment_id": "fragment01", "asset_id": "asset-1"}],
            profiles=[{"asset_id": "asset-1", "width": 200, "height": 400, "overlay_detected": False}],
            media_type="image",
        )
        report = self.build()
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["blocked_fragment_ids"], ["fragment01"])

    def test_missing_profiles_surfaces_manual_review(self) -> None:
        self.write(
            plan_fragments=[{"fragment_id": "fragment01", "asset_id": "asset-unknown"}],
            profiles=[],
            media_type="image",
        )
        report = self.build()
        self.assertEqual(report["status"], "manual_review")
        self.assertEqual(report["fragments"][0]["readability_status"], "manual_review")

    def test_invalid_artifact_inputs_are_rejected(self) -> None:
        self.write(
            plan_fragments=[{"fragment_id": "fragment01", "asset_id": "asset-1"}],
            profiles=[],
            media_type="image",
        )
        atomic_write_json(self.root / "asset_profiles.json", {"artifact_type": "wrong"})
        with self.assertRaises(VisualLayoutError):
            self.build()


if __name__ == "__main__":
    unittest.main()
