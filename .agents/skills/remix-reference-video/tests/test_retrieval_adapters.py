from __future__ import annotations

import unittest

from remix_reference_video.adapters.retrieval import RetrievalAdapter, RetrievalError


class RetrievalAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fragments = [
            {
                "fragment_id": f"fragment0{index}",
                "requirements": {
                    "product_type": "tablemat",
                    "required_semantics": ["proof.clean"],
                    "required_actions": ["wipe"],
                    "scene_tags": ["dining_table"],
                    "allowed_media_types": ["video"],
                    "forbidden_semantics": ["other_product"],
                    "expected_visual_seconds": 1.5,
                },
            }
            for index in range(1, 4)
        ]
        self.baseline = {
            "artifact_type": "content_baseline",
            "fragments": self.fragments,
        }
        self.assets = [
            self.asset("a", "source-a", "hash-a", "phash-a", 0.95),
            self.asset("a-copy", "source-copy", "hash-copy", "phash-a", 0.94),
            self.asset("b", "source-b", "hash-b", "phash-b", 0.80),
        ]

    @staticmethod
    def asset(
        asset_id: str, source_id: str, sha256: str, perceptual_hash: str, score: float
    ) -> dict[str, object]:
        return {
            "asset_id": asset_id,
            "source_id": source_id,
            "source_path": f"{asset_id}.mp4",
            "sha256": sha256,
            "perceptual_hash": perceptual_hash,
            "media_type": "video",
            "duration_seconds": 4.0,
            "product_type": "tablemat",
            "semantic_tags": ["proof.clean"],
            "action_tags": ["wipe"],
            "scene_tags": ["dining_table"],
            "scores": {
                "semantic": score,
                "action": score,
                "composition": score,
                "color": score,
                "lighting": score,
                "technical": score,
            },
            "overlay_detected": True,
            "broad_ranges": [{"start_seconds": 0.5, "end_seconds": 3.0}],
        }

    def test_authoritative_coverage_requires_current_gate2(self) -> None:
        adapter = RetrievalAdapter()
        precheck = adapter.build_coverage(
            scope="precheck",
            content_baseline=self.baseline,
            asset_profiles=self.assets,
            gate2_approved=False,
        )
        self.assertEqual(precheck["authority"], "advisory_only")
        with self.assertRaisesRegex(RetrievalError, "Gate 2"):
            adapter.build_coverage(
                scope="authoritative",
                content_baseline=self.baseline,
                asset_profiles=self.assets,
                gate2_approved=False,
            )

    def test_qualification_scoring_duplicate_suppression_and_missing_block(self) -> None:
        adapter = RetrievalAdapter()
        report = adapter.match_assets(
            content_baseline=self.baseline,
            asset_profiles=self.assets,
            gate2_approved=True,
        )

        first = report["fragments"][0]
        self.assertEqual([row["asset_id"] for row in first["candidates"]], ["a", "b"])
        self.assertEqual(first["candidates"][0]["confidence"], 0.95)
        broken = [dict(self.assets[0], product_type="other")]
        missing = adapter.match_assets(
            content_baseline=self.baseline,
            asset_profiles=broken,
            gate2_approved=True,
        )
        self.assertEqual(missing["status"], "blocked")
        self.assertEqual(missing["fragments"][0]["status"], "missing_material")

    def test_global_schedule_and_review_package_include_overlay_and_broad_range(self) -> None:
        adapter = RetrievalAdapter()
        matches = adapter.match_assets(
            content_baseline=self.baseline,
            asset_profiles=self.assets,
            gate2_approved=True,
        )
        self.assertEqual(
            [row["selected_asset_id"] for row in matches["fragments"]],
            ["a", "a", "b"],
        )
        package = adapter.build_candidate_review_package(
            matches=matches,
            overlay_decisions={
                "fragment01": "retain_source_text",
                "fragment02": "cover",
                "fragment03": "no_action",
            },
        )
        self.assertEqual(package["gate_id"], "gate3_material_selection")
        self.assertEqual(package["selections"][1]["overlay_policy"], "cover")
        self.assertEqual(package["selections"][1]["source_path"], "a.mp4")
        self.assertEqual(package["selections"][1]["media_type"], "video")
        self.assertEqual(
            package["selections"][1]["approved_broad_range"],
            {"start_seconds": 0.5, "end_seconds": 3.0},
        )
        with self.assertRaisesRegex(RetrievalError, "overlay policy"):
            adapter.build_candidate_review_package(
                matches=matches,
                overlay_decisions={row["fragment_id"]: "blur" for row in matches["fragments"]},
            )


if __name__ == "__main__":
    unittest.main()
