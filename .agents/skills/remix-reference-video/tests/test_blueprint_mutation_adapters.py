from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from remix_reference_video.adapters.blueprint import (
    BlueprintAdapter,
    BlueprintValidationError,
)
from remix_reference_video.adapters.mutation import (
    ControlledMutationAdapter,
    MutationValidationError,
    gate2_stale_projection,
)
from remix_reference_video.storage import atomic_write_json


class BlueprintMutationAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.brief = {
            "approved_claims": [
                {"claim_id": "clean", "text": "污渍可以擦净"},
                {"claim_id": "water", "text": "日常防泼水"},
            ],
            "approved_fallbacks": [
                {
                    "fallback_id": "water-observed",
                    "claim_id": "water",
                    "text": "水滴停留在表面",
                }
            ],
            "forbidden_claims": ["绝对防水"],
            "duration_envelope": {
                "minimum_seconds": 11.0,
                "maximum_seconds": 18.0,
                "strength": "soft",
            },
            "maximum_narration_chars_per_second": 5.0,
        }
        self.recipe = {
            "artifact_type": "recipe",
            "shots": [{"shot_id": "shot_001"}],
        }
        self.precheck = {
            "artifact_type": "coverage_precheck",
            "scope": "precheck",
            "coverage": [{"narrative_function": "proof", "status": "likely"}],
        }
        self.fragments = [
            {
                "fragment_id": "fragment01",
                "reference_shot_ids": ["shot_001"],
                "narrative_function": "proof",
                "narrative_role": "功能证明",
                "required_actions": ["demonstrate_feature"],
                "claim_ids": ["clean"],
                "narration": "污渍可以擦净",
            }
        ]

    def test_blueprint_uses_precheck_as_advisory_not_authoritative_coverage(self) -> None:
        result = BlueprintAdapter().compile(
            brief=self.brief,
            recipe=self.recipe,
            coverage_precheck=self.precheck,
            target_fragments=self.fragments,
        )

        self.assertEqual(result["shot_blueprint"]["coverage_role"], "advisory_only")
        self.assertEqual(result["content_baseline"]["claims"][0]["claim_id"], "clean")
        authoritative = dict(self.precheck, artifact_type="coverage_report", scope="authoritative")
        with self.assertRaisesRegex(BlueprintValidationError, "coverage_precheck"):
            BlueprintAdapter().compile(
                brief=self.brief,
                recipe=self.recipe,
                coverage_precheck=authoritative,
                target_fragments=self.fragments,
            )

    def test_blueprint_rejects_new_or_forbidden_claims(self) -> None:
        fragments = [dict(self.fragments[0], claim_ids=["absolute-waterproof"])]
        with self.assertRaisesRegex(BlueprintValidationError, "unapproved claim"):
            BlueprintAdapter().compile(
                brief=self.brief,
                recipe=self.recipe,
                coverage_precheck=self.precheck,
                target_fragments=fragments,
            )

    def test_gate2_package_binds_baseline_and_mutation_and_lints_fallback(self) -> None:
        compiled = BlueprintAdapter().compile(
            brief=self.brief,
            recipe=self.recipe,
            coverage_precheck=self.precheck,
            target_fragments=self.fragments,
        )
        adapter = ControlledMutationAdapter()
        mutation = adapter.compile(
            brief=self.brief,
            content_baseline=compiled["content_baseline"],
            fallback_ids=["water-observed"],
        )
        baseline_path = self.root / "content_baseline.json"
        mutation_path = self.root / "mutation_plan.json"
        atomic_write_json(baseline_path, compiled["content_baseline"])
        atomic_write_json(mutation_path, mutation)
        package = adapter.build_gate2_package(
            content_baseline_path=baseline_path,
            mutation_plan_path=mutation_path,
            run_id="run-1",
            state_revision=3,
            created_at="2026-08-15T12:00:00Z",
        )

        self.assertEqual(package["gate_id"], "gate2")
        self.assertEqual(package["approval_mode"], "atomic")
        self.assertEqual(package["run_id"], "run-1")
        self.assertEqual(package["state_revision"], 3)
        self.assertEqual(
            set(package["input_hashes"]),
            {"content_baseline.json", "mutation_plan.json"},
        )
        with self.assertRaisesRegex(MutationValidationError, "unapproved fallback"):
            adapter.compile(
                brief=self.brief,
                content_baseline=compiled["content_baseline"],
                fallback_ids=["invented"],
            )

    def test_soft_timing_lint_expands_duration_and_gate2_changes_propagate_stale(self) -> None:
        long_fragments = [dict(self.fragments[0], narration="需要完整保留的有效叙事内容" * 10)]
        compiled = BlueprintAdapter().compile(
            brief=self.brief,
            recipe=self.recipe,
            coverage_precheck=self.precheck,
            target_fragments=long_fragments,
        )

        timing = compiled["content_baseline"]["timing_lint"]
        self.assertEqual(timing["status"], "duration_expansion_required")
        self.assertGreater(timing["recommended_duration_seconds"], 18.0)
        stale = gate2_stale_projection({"fallback", "content_baseline"})
        self.assertEqual(stale["gate_status"]["gate2"], "stale")
        self.assertEqual(stale["gate_status"]["gate5"], "stale")
        self.assertNotIn("recipe.json", stale["derived_artifacts"])
        self.assertNotIn("shared_asset_index", stale["derived_artifacts"])


if __name__ == "__main__":
    unittest.main()
