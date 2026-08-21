from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from remix_reference_video.creative_baseline import CreativeBaselineComparison, CreativeBaselineError
from remix_reference_video.storage import atomic_write_json


class CreativeBaselineComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.v0 = self.root / "baseline-v0"
        self.v1 = self.root / "baseline-v1"
        self.v0.mkdir()
        self.v1.mkdir()
        self._write_run(self.v0, run_id="gb-cold-1786890259", creative=False)
        self._write_run(self.v1, run_id="creative-cold-1", creative=True)

    def _write_run(self, root: Path, *, run_id: str, creative: bool) -> None:
        (root / "reference-2026-08-16.mp4").write_bytes(b"reference")
        (root / "asset-a.jpg").write_bytes(b"asset")
        atomic_write_json(root / "project_brief.json", {
            "product_name": "透明桌垫", "approved_claims": ["极简透明"],
            "forbidden_claims": ["未经批准声明"], "audience": "精致白领", "platform": "抖音",
            "voice": {"speaker": "zh_female", "speed": 1.0},
            "output": {"width": 1080, "height": 1920, "fps": 60},
        })
        atomic_write_json(root / "g_b_frozen_input_snapshot.json", {
            "reference_sha256": "reference", "brief_sha256": "brief", "asset_profiles_sha256": "profiles",
            "asset_snapshot": {"asset-a.jpg": "asset"},
            **({"creative_contract_version": "creative_contract_v1"} if creative else {}),
        })
        atomic_write_json(root / "pipeline_state.json", {"run_id": run_id})
        atomic_write_json(root / "final_validation_report.json", {"status": "passed"})

    def test_registers_only_the_named_cold_run_as_baseline_v0(self) -> None:
        comparison = CreativeBaselineComparison()
        registered = comparison.register_baseline_v0(self.v0, video_version_id="video-v0")
        self.assertEqual(registered["baseline_id"], "baseline_v0")
        self.assertEqual(registered["run_id"], "gb-cold-1786890259")
        self.assertEqual(registered["video_version_id"], "video-v0")
        with self.assertRaisesRegex(CreativeBaselineError, "gb-cold-1786890259"):
            comparison.register_baseline_v0(self.v1, video_version_id="wrong")

    def test_comparison_fixes_inputs_and_allows_only_creative_making_deltas(self) -> None:
        comparison = CreativeBaselineComparison()
        baseline = comparison.register_baseline_v0(self.v0, video_version_id="video-v0")
        prepared = comparison.prepare(baseline, self.v1, video_version_id="video-v1")
        self.assertFalse(prepared["ai_enhancement_enabled"])
        self.assertEqual(prepared["allowed_deltas"], [
            "selected_decomposition", "selected_remix_strategy", "script", "material_selection_and_range", "timeline", "final_video",
        ])
        self.assertNotEqual(prepared["v0"]["evaluation_context_id"], prepared["v1"]["evaluation_context_id"])
        self.assertEqual(prepared["v0"]["comparison_id"], prepared["v1"]["comparison_id"])

    def test_evaluation_requires_strict_creative_improvement_and_no_regression(self) -> None:
        comparison = CreativeBaselineComparison()
        prepared = comparison.prepare(comparison.register_baseline_v0(self.v0, video_version_id="video-v0"), self.v1, video_version_id="video-v1")
        v0 = {"first_three_seconds": "ordinary", "script_coherence": "ordinary", "visual_consistency": "ordinary", "highlights": "ordinary", "viewing_experience": "ordinary"}
        v1 = {"first_three_seconds": "high", "script_coherence": "high", "visual_consistency": "ordinary", "highlights": "high", "viewing_experience": "ordinary"}
        result = comparison.evaluate(
            prepared, v0_evaluation=v0, v1_evaluation=v1,
            v1_required_objectives_passed=True, v1_claim_evidence_passed=True,
            v0_l0_passed=True, v1_l0_passed=True, no_unapproved_inputs=True,
        )
        self.assertEqual(result["status"], "passed")

        regressed = comparison.evaluate(
            prepared, v0_evaluation=v0, v1_evaluation={**v1, "first_three_seconds": "ordinary"},
            v1_required_objectives_passed=True, v1_claim_evidence_passed=True,
            v0_l0_passed=True, v1_l0_passed=True, no_unapproved_inputs=True,
        )
        self.assertEqual(regressed["status"], "blocked")
        self.assertIn("first_three_seconds_not_strictly_improved", regressed["failed_checks"])


if __name__ == "__main__":
    unittest.main()
