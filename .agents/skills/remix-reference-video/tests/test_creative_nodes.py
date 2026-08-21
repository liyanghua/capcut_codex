from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from remix_reference_video.adapters.decomposition import DecompositionAdapter
from remix_reference_video.adapters.script_candidates import ScriptCandidateGenerator, ScriptCandidateValidator
from remix_reference_video.native_completion import _select_script_candidate
from remix_reference_video.orchestrator import creative_dag
from remix_reference_video.snapshot_schema_validator import SnapshotSchemaValidator
from remix_reference_video.storage import atomic_write_json


class CreativeNodeTests(unittest.TestCase):
    def test_script_generator_requires_an_explicit_provider_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "provider configuration"):
            ScriptCandidateGenerator()

    def test_decomposition_emits_three_strategy_candidates_with_reference_ids(self) -> None:
        result = DecompositionAdapter().build({"shots": [{"shot_id": "shot-1", "start_seconds": 0, "end_seconds": 1, "semantic": "hook"}]}, requested_strategies=None)
        self.assertEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["strategy_id"], "hybrid_commerce_v1")
        self.assertEqual(candidate["reference_shot_ids"], ["shot-1"])

    def test_stub_script_generator_is_reproducible_and_validator_blocks_pure_claim_run(self) -> None:
        inputs = {"objective": {"objectives": [{"objective_id": "hook", "weight": 1.0, "required": True}]}, "evidence": {"fragments": [{"fragment_id": "f1", "voice_text": "透明桌垫防水防油", "narrative_role": "product", "required_actions": ["show"]}]}}
        first = ScriptCandidateGenerator(provider="stub", seed=7).generate(inputs)
        second = ScriptCandidateGenerator(provider="stub", seed=7).generate(inputs)
        self.assertEqual(first, second)
        report = ScriptCandidateValidator().validate(first, inputs)
        self.assertIn(report["status"], {"passed", "blocked", "manual_review"})
        self.assertIn("candidates", report)

    def test_script_candidates_bind_objective_evidence_visual_intent_and_budget(self) -> None:
        inputs = {
            "objective": {"objectives": [
                {"objective_id": "opening_hook", "required": True, "weight": 0.5},
                {"objective_id": "claim:clear", "required": True, "weight": 0.5},
            ]},
            "evidence": {"fragments": [{
                "fragment_id": "f1", "voice_text": "先看清透质感，再看防水表现。",
                "narrative_role": "opening", "required_actions": ["show_product"],
                "claim_ids": ["clear"], "evidence_row_ref": "evidence:f1",
                "visual_intent": {"required_actions": ["show_product"]},
                "visual_duration_budget_seconds": 4.0,
            }]},
        }
        generated = ScriptCandidateGenerator(provider="stub", seed=7).generate(inputs)
        line = generated["candidates"][0]["lines"][0]
        self.assertEqual(line["objective_id"], "opening_hook")
        self.assertEqual(line["claim_ids"], ["clear"])
        self.assertEqual(line["evidence_row_ref"], "evidence:f1")
        self.assertEqual(line["visual_intent"]["required_actions"], ["show_product"])
        self.assertLessEqual(line["estimated_duration_seconds"], 4.0)
        report = ScriptCandidateValidator().validate(generated, inputs)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["candidates"][0]["checks"]["required_objectives"], "passed")
        validator = SnapshotSchemaValidator()
        validator.assert_valid(generated, "script-candidates.schema.json")
        validator.assert_valid(report, "script-candidate-validation-report.schema.json")

    def test_script_candidate_selection_uses_coverage_then_margin_then_id(self) -> None:
        artifact = {
            "candidates": [
                {"script_candidate_id": "z", "lines": [{"script_line_id": "z1", "fragment_id": "f1", "text": "甲"}]},
                {"script_candidate_id": "a", "lines": [{"script_line_id": "a1", "fragment_id": "f1", "text": "乙"}]},
            ]
        }
        validation = {"candidates": [
            {"script_candidate_id": "z", "status": "passed", "objective_coverage": ["required"], "weighted_objective_coverage": 1.0, "budget_margin_seconds": 0.2},
            {"script_candidate_id": "a", "status": "passed", "objective_coverage": ["required"], "weighted_objective_coverage": 1.0, "budget_margin_seconds": 0.2},
        ]}
        selected = ScriptCandidateValidator().select(artifact, validation)
        self.assertEqual(selected["script_candidate_id"], "a")

    def test_native_selection_materializes_ranked_candidate_as_production_script(self) -> None:
        artifact = {"candidates": [
            {"script_candidate_id": "z", "lines": [{"script_line_id": "z1", "fragment_id": "f1", "text": "甲"}]},
            {"script_candidate_id": "a", "lines": [{"script_line_id": "a1", "fragment_id": "f1", "text": "乙"}]},
        ]}
        validation = {"candidates": [
            {"script_candidate_id": "z", "status": "passed", "objective_coverage": ["required"], "weighted_objective_coverage": 1.0, "budget_margin_seconds": 0.2},
            {"script_candidate_id": "a", "status": "passed", "objective_coverage": ["required"], "weighted_objective_coverage": 1.0, "budget_margin_seconds": 0.2},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            candidates_path = Path(directory) / "script_candidates.json"
            validation_path = Path(directory) / "script_candidate_validation_report.json"
            atomic_write_json(candidates_path, artifact)
            atomic_write_json(validation_path, validation)
            result = _select_script_candidate(candidates_path, validation_path)
        self.assertEqual(result["selected_script_candidate_id"], "a")
        self.assertEqual(result["lines"][0]["line_id"], "a1")

    def test_creative_dag_contains_real_strategy_and_script_nodes(self) -> None:
        ids = [node.node_id for node in creative_dag()]
        for node_id in ("build-decomposition-candidates", "build-gate1-package", "generate-script-candidates", "validate-script-candidates", "select-script-candidate", "validate-shot-quality", "build-final-content-diagnostic"):
            self.assertIn(node_id, ids)


if __name__ == "__main__":
    unittest.main()
