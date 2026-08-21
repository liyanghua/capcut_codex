from __future__ import annotations

import unittest

from remix_reference_video.adapters.mutation import ControlledMutationAdapter


class RemixStrategyCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = {
            "artifact_type": "content_baseline",
            "fragments": [
                {"fragment_id": "fragment01", "claim_ids": ["clear"]},
                {"fragment_id": "fragment02", "claim_ids": ["water"]},
            ],
        }
        self.precheck = {
            "artifact_type": "coverage_precheck",
            "scope": "precheck",
            "coverage": [
                {"fragment_id": "fragment01", "status": "likely"},
                {"fragment_id": "fragment02", "status": "missing"},
            ],
        }
        self.objective = {
            "artifact_type": "creative_objective",
            "objective_id": "objective-001",
        }

    def test_candidates_are_bounded_and_derived_from_precheck(self) -> None:
        result = ControlledMutationAdapter().build_remix_strategy_candidates(
            content_baseline=self.baseline,
            coverage_precheck=self.precheck,
            creative_objective=self.objective,
            selected_decomposition_id="decomp-001",
        )

        self.assertEqual(result["artifact_type"], "remix_strategy_candidates")
        self.assertEqual(result["objective_id"], "objective-001")
        self.assertEqual(result["selected_decomposition_id"], "decomp-001")
        self.assertLessEqual(len(result["candidates"]), 3)
        self.assertIn(
            "balanced_remix_v1",
            [row["strategy_id"] for row in result["candidates"]],
        )
        balanced = next(row for row in result["candidates"] if row["strategy_id"] == "balanced_remix_v1")
        self.assertEqual(balanced["coverage_estimate"], 0.5)
        self.assertEqual(balanced["feasibility_estimate"], 0.5)
        for section in ("preserve", "replace", "compress", "expand", "reorder", "fallback"):
            self.assertIn(section, balanced)

    def test_strategy_inputs_require_precheck_and_objective_contracts(self) -> None:
        adapter = ControlledMutationAdapter()
        with self.assertRaisesRegex(ValueError, "coverage_precheck"):
            adapter.build_remix_strategy_candidates(
                content_baseline=self.baseline,
                coverage_precheck={"artifact_type": "coverage_report", "scope": "authoritative"},
                creative_objective=self.objective,
                selected_decomposition_id="decomp-001",
            )
        with self.assertRaisesRegex(ValueError, "creative_objective"):
            adapter.build_remix_strategy_candidates(
                content_baseline=self.baseline,
                coverage_precheck=self.precheck,
                creative_objective={"artifact_type": "other"},
                selected_decomposition_id="decomp-001",
            )


if __name__ == "__main__":
    unittest.main()
