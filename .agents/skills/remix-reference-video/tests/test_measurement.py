from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from remix_reference_video.measurement import (
    FrozenPairHarness,
    MeasurementError,
    Phase6Snapshot,
)


class MeasurementTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.harness = FrozenPairHarness()

    def test_cold_cache_must_be_empty_and_hot_cache_is_cloned_snapshot(self) -> None:
        cold = self.root / "cold"
        hot = self.root / "hot"
        cold.mkdir()
        (cold / "index.sqlite3").write_bytes(b"cold-result")
        self.harness.clone_hot_cache(cold_cache=cold, hot_cache=hot)
        self.assertEqual((hot / "index.sqlite3").read_bytes(), b"cold-result")
        with self.assertRaisesRegex(MeasurementError, "empty cold cache"):
            self.harness.assert_empty_cold_cache(cold)
        empty = self.root / "empty"
        empty.mkdir()
        self.harness.assert_empty_cold_cache(empty)

    def test_pair_requires_controlled_mutation_and_separate_approvals(self) -> None:
        base = {"reference": "r1", "brief": "b1", "visual_asset": "a1"}
        mutated = {"reference": "r1", "brief": "b1", "visual_asset": "a2"}
        self.harness.validate_controlled_mutation(base, mutated, {"visual_asset"})
        with self.assertRaisesRegex(MeasurementError, "uncontrolled mutation"):
            self.harness.validate_controlled_mutation(base, dict(mutated, brief="b2"), {"visual_asset"})
        self.harness.validate_separate_approvals(
            {"run_id": "v1", "decision_ids": ["d1"]},
            {"run_id": "v2", "decision_ids": ["d2"]},
        )
        with self.assertRaisesRegex(MeasurementError, "approval reuse"):
            self.harness.validate_separate_approvals(
                {"run_id": "v1", "decision_ids": ["d1"]},
                {"run_id": "v2", "decision_ids": ["d1"]},
            )

    def test_snapshot_separates_machine_human_touch_rework_and_cache(self) -> None:
        snapshot = Phase6Snapshot().build(
            stage_scores={
                "performance_proven_video": 90,
                "blueprint": 89,
                "controlled_mutation": 88,
                "retrieval": 90,
                "reconstruction": 93,
            },
            metrics={
                "machine_api_critical_path_seconds": 700,
                "human_wait_seconds": 1200,
                "operator_touch_seconds": 180,
                "rework_seconds": 30,
                "gate_return_count": 1,
            },
            cache_status="cold",
            v1_metrics={"rework_seconds": 40, "gate_return_count": 2},
        )
        self.assertEqual(snapshot["video_quality_score"], 90.0)
        self.assertEqual(snapshot["machine_api_critical_path_seconds"], 700)
        self.assertEqual(snapshot["human_wait_seconds"], 1200)
        self.assertTrue(snapshot["g_b_thresholds_met"])
        self.assertEqual(snapshot["target_video_quality_score"], 91)

    def test_v1_comparability_and_cross_run_cache_isolation_are_required(self) -> None:
        with self.assertRaisesRegex(MeasurementError, "V1 comparability"):
            Phase6Snapshot().build(
                stage_scores={stage: 90 for stage in Phase6Snapshot.STAGES},
                metrics={
                    "machine_api_critical_path_seconds": 400,
                    "human_wait_seconds": 0,
                    "operator_touch_seconds": 0,
                    "rework_seconds": 0,
                    "gate_return_count": 0,
                },
                cache_status="hot",
                v1_metrics=None,
            )
        allowed = self.root / "run-v2-cache"
        allowed.mkdir()
        self.harness.validate_cache_reads(
            [allowed / "stage.json"], allowed_cache_root=allowed
        )
        with self.assertRaisesRegex(MeasurementError, "cross-run cache"):
            self.harness.validate_cache_reads(
                [self.root / "run-v1-cache/stage.json"], allowed_cache_root=allowed
            )


if __name__ == "__main__":
    unittest.main()
