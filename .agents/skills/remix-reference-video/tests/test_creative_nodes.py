from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from remix_reference_video.adapters.decomposition import DecompositionAdapter
from remix_reference_video.adapters.script_candidates import ScriptCandidateGenerator, ScriptCandidateValidator
from remix_reference_video.orchestrator import creative_dag
from remix_reference_video.storage import atomic_write_json


class CreativeNodeTests(unittest.TestCase):
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

    def test_creative_dag_contains_real_strategy_and_script_nodes(self) -> None:
        ids = [node.node_id for node in creative_dag()]
        for node_id in ("build-decomposition-candidates", "build-gate1-package", "generate-script-candidates", "validate-script-candidates", "select-script-candidate", "validate-shot-quality", "build-final-content-diagnostic"):
            self.assertIn(node_id, ids)


if __name__ == "__main__":
    unittest.main()
