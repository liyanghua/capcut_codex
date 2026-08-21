from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from remix_reference_video.native_planning import _compile_blueprint, _compile_mutation
from remix_reference_video.native_preparation import _gate2_package
from remix_reference_video.storage import atomic_write_json


class CreativeGate2ProductionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.brief = self.root / "project_brief.json"
        self.recipe = self.root / "recipe.json"
        self.precheck = self.root / "coverage_precheck.json"
        atomic_write_json(self.brief, {
            "approved_claims": [{"claim_id": "clear", "text": "极简透明"}],
            "forbidden_claims": [], "approved_fallbacks": [],
            "product": {"name": "透明桌垫", "audience": "精致白领"},
            "target": {"platform": "抖音"},
            "duration_envelope": {"minimum_seconds": 10, "maximum_seconds": 20, "strength": "soft"},
            "maximum_narration_chars_per_second": 5.0,
        })
        atomic_write_json(self.recipe, {"artifact_type": "recipe", "shots": [{"shot_id": "shot-1"}]})
        atomic_write_json(self.precheck, {"artifact_type": "coverage_precheck", "scope": "precheck", "coverage": [{"fragment_id": "fragment01", "status": "likely"}]})

    def test_creative_native_steps_emit_gate2_artifacts_from_selected_decomposition(self) -> None:
        blueprint = _compile_blueprint(
            self.brief, self.recipe, self.precheck,
            {"selected_decomposition_id": "decomp-001", "target_fragments": [{
                "fragment_id": "fragment01", "claim_ids": ["clear"], "narration": "极简透明",
                "narrative_role": "产品出现", "required_actions": ["show_product"],
            }]},
            creative=True, gate1_selection_hash="c" * 64,
        )
        self.assertIn("creative_objective", blueprint)
        baseline = self.root / "content_baseline.json"
        objective = self.root / "creative_objective.json"
        atomic_write_json(baseline, blueprint["content_baseline"])
        atomic_write_json(objective, blueprint["creative_objective"])

        mutation = _compile_mutation(
            self.brief, baseline, self.precheck, objective,
            {"selected_decomposition_id": "decomp-001", "fallback_ids": []}, creative=True,
        )
        self.assertIn("mutation_plan", mutation)
        self.assertIn("remix_strategy_candidates", mutation)
        self.assertEqual(mutation["remix_strategy_candidates"]["objective_id"], blueprint["creative_objective"]["objective_id"])

    def test_creative_gate2_package_requires_and_binds_all_creative_inputs(self) -> None:
        state = self.root / "pipeline_state.json"
        baseline = self.root / "content_baseline.json"
        mutation = self.root / "mutation_plan.json"
        atomic_write_json(state, {"run_id": "run-1", "state_revision": 2})
        atomic_write_json(baseline, {"artifact_type": "content_baseline"})
        atomic_write_json(mutation, {"artifact_type": "mutation_plan"})
        atomic_write_json(self.root / "g_b_frozen_input_snapshot.json", {"creative_contract_version": "creative_contract_v1"})
        with self.assertRaisesRegex(ValueError, "creative Gate 2"):
            _gate2_package(self.root, baseline, mutation, state)

        atomic_write_json(self.root / "creative_objective.json", {"artifact_type": "creative_objective"})
        atomic_write_json(self.root / "coverage_precheck.json", {"artifact_type": "coverage_precheck"})
        atomic_write_json(self.root / "remix_strategy_candidates.json", {
            "artifact_type": "remix_strategy_candidates",
            "candidates": [{"strategy_id": "balanced_remix_v1", "status": "passed"}],
        })
        package = _gate2_package(self.root, baseline, mutation, state)
        self.assertEqual(
            set(package["input_hashes"]),
            {"content_baseline.json", "mutation_plan.json", "creative_objective.json", "remix_strategy_candidates.json", "coverage_precheck.json"},
        )
        self.assertEqual(package["creative_bindings"]["selected_remix_strategy_id"], "balanced_remix_v1")


if __name__ == "__main__":
    unittest.main()
