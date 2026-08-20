from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.adapters.retrieval import RetrievalAdapter
from remix_reference_video.material_evidence import (
    MaterialEvidenceError,
    build_material_evidence_requirements,
    merge_material_evidence,
)


class MaterialEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = {"artifact_type": "content_baseline", "fragments": [{
            "fragment_id": "fragment01", "requirements": {
                "product_type": "透明桌垫", "required_semantics": ["claim-a"],
                "required_actions": ["show_product"], "allowed_media_types": ["image", "video"],
                "forbidden_semantics": [], "expected_visual_seconds": 1.0,
            },
        }]}
        self.profiles = [{
            "asset_id": "asset-a", "source_path": "images/a.jpg", "sha256": "a" * 64,
            "media_type": "image", "width": 1080, "height": 1920, "duration_seconds": None,
        }]

    def _annotations(self) -> dict[str, object]:
        return {
            "artifact_type": "material_evidence_annotations",
            "input_hashes": {"asset_profiles.json": "b" * 64, "material_evidence_requirements.json": "c" * 64},
            "annotations": [{
                "asset_id": "asset-a", "source_path": "images/a.jpg", "sha256": "a" * 64,
                "evidence_source": "manual_operator", "product_type": "透明桌垫",
                "semantic_tags": ["claim-a"], "action_tags": ["show_product"],
                "overlay_decision": "retain_source_text",
                "evidence_window": {"kind": "frame", "frame_path": "images/a.jpg"},
                "scores": {"semantic": 1.0, "action": 1.0, "composition": 0.8, "color": 0.8, "lighting": 0.8, "technical": 1.0},
                "score_basis": "人工逐帧确认",
            }],
        }

    def test_missing_annotation_requires_manual_classification_and_is_not_selectable(self) -> None:
        requirements = build_material_evidence_requirements(self.baseline, self.profiles, None)
        self.assertEqual(requirements["status"], "manual_classification_required")
        self.assertEqual(requirements["requirements"][0]["missing_fields"], ["product_type", "semantic_tags", "action_tags", "overlay_decision", "evidence_window"])
        merged = merge_material_evidence(self.profiles, None)
        self.assertEqual(merged["profiles"], [])
        self.assertEqual(merged["blockers"][0]["category"], "manual_classification_required")

    def test_current_annotation_is_only_business_evidence_used_by_retrieval(self) -> None:
        merged = merge_material_evidence(self.profiles, self._annotations())
        self.assertEqual(len(merged["profiles"]), 1)
        profile = merged["profiles"][0]
        self.assertEqual(profile["product_type"], "透明桌垫")
        report = RetrievalAdapter().match_assets(
            content_baseline=self.baseline, asset_profiles=merged["profiles"], gate2_approved=True,
        )
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["fragments"][0]["selected_asset_id"], "asset-a")
        self.assertNotIn("product_type", self.profiles[0])

    def test_annotation_hash_mismatch_duplicate_and_unreviewable_window_fail_closed(self) -> None:
        for mutate, message in (
            (lambda value: value["annotations"][0].update(sha256="d" * 64), "hash"),
            (lambda value: value["annotations"].append(dict(value["annotations"][0])), "duplicate"),
            (lambda value: value["annotations"][0].update(evidence_window={"kind": "frame", "frame_path": ""}), "window"),
        ):
            value = self._annotations()
            mutate(value)
            with self.subTest(message):
                with self.assertRaisesRegex(MaterialEvidenceError, message):
                    merge_material_evidence(self.profiles, value)


if __name__ == "__main__":
    unittest.main()
