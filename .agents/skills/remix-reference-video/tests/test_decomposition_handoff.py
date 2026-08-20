from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.approvals import ApprovalService
from remix_reference_video.decomposition_handoff import (
    DecompositionHandoffError,
    build_gate1_package,
    materialize_approved_decomposition,
)
from remix_reference_video.stage_input_validator import StageInputValidator
from remix_reference_video.storage import TaskStorage, atomic_write_json, read_json_object


class DecompositionHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = TaskStorage(self.root)
        self.store.initialize_state({
            "execution_mode": "track-b-production", "run_id": "creative-run", "state_revision": 0,
            "active_stage": "performance_proven_video", "active_command": None, "stage_status": {},
            "gate_status": {"gate1": "awaiting_user", "gate2": "not_ready", "gate3_material_selection": "not_ready", "gate3_evidence_closure": "not_ready", "gate3": "not_ready", "gate4_pre_generation": "not_ready", "gate4_post_generation": "not_ready", "gate4": "not_ready", "gate5": "not_ready"},
            "decisions": [], "artifacts": {}, "blockers": [], "cache_summary": {},
        })
        atomic_write_json(self.root / "g_b_frozen_input_snapshot.json", {"creative_contract_version": "creative_contract_v1"})
        atomic_write_json(self.root / "recipe.json", {"artifact_type": "recipe", "shots": [{"shot_id": "s1", "start_seconds": 0, "end_seconds": 1}, {"shot_id": "s2", "start_seconds": 1, "end_seconds": 2}]})
        atomic_write_json(self.root / "project_brief.json", {
            "artifact_type": "project_brief", "approved_claims": [
                {"claim_id": "claim-a", "text": "极简透明"}, {"claim_id": "claim-b", "text": "防水防油"},
            ], "forbidden_claims": [], "approved_fallbacks": [],
        })
        atomic_write_json(self.root / "decomposition_bundle.json", {
            "artifact_type": "decomposition_bundle", "bundle_version": "decomposition_bundle_v1",
            "candidates": [
                {"decomposition_id": "decomp-a", "strategy_id": "structure_semantic_v1", "segments": [{"segment_id": "a1", "reference_shot_id": "s1", "semantic_role": "opening", "required_actions": []}]},
                {"decomposition_id": "decomp-b", "strategy_id": "hybrid_commerce_v1", "segments": [
                    {"segment_id": "b1", "reference_shot_id": "s1", "semantic_role": "opening", "required_actions": []},
                    {"segment_id": "b2", "reference_shot_id": "s2", "semantic_role": "close", "required_actions": []},
                ]},
            ],
        })

    @staticmethod
    def _sha(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def _approve_second(self) -> None:
        package = build_gate1_package(self.root)
        self.assertNotIn("selected_decomposition_id", package.get("creative_bindings", {}))
        package_path = self.root / "gate_review_packages" / "gate1.json"
        atomic_write_json(package_path, package)
        decision = self.root / "decision.json"
        atomic_write_json(decision, {"decision": "approved", "scope_type": "artifact_set", "scope_ids": ["decomposition_bundle.json"], "strategy": {"selected_decomposition_id": "decomp-b"}})
        ApprovalService(self.store).approve(
            gate_id="gate1", review_package_hash=self._sha(package_path), decision_file=decision, actor="owner",
        )

    def test_real_gate1_selection_materializes_only_selected_candidate(self) -> None:
        self._approve_second()
        result = materialize_approved_decomposition(self.root)
        self.assertEqual(result["selected_decomposition_id"], "decomp-b")
        blueprint = read_json_object(self.root / "stage_inputs" / "compile-blueprint.json")
        mutation = read_json_object(self.root / "stage_inputs" / "compile-mutation-plan.json")
        self.assertEqual(blueprint["payload"]["selected_decomposition_id"], "decomp-b")
        self.assertEqual(len(blueprint["payload"]["target_fragments"]), 2)
        self.assertEqual(mutation["payload"]["fallback_ids"], [])
        self.assertTrue(StageInputValidator(self.root).validate(self.root / "stage_inputs" / "compile-blueprint.json", expected_stage_id="compile-blueprint").valid)
        self.assertTrue(StageInputValidator(self.root).validate(self.root / "stage_inputs" / "compile-mutation-plan.json", expected_stage_id="compile-mutation-plan").valid)

    def test_handoff_rejects_forged_approved_state_without_decision(self) -> None:
        self.store.update_state(lambda state: state | {"gate_status": {**state["gate_status"], "gate1": "approved"}})
        with self.assertRaisesRegex(DecompositionHandoffError, "decision"):
            materialize_approved_decomposition(self.root)

    def test_handoff_rejects_bundle_drift_after_approval(self) -> None:
        self._approve_second()
        bundle = read_json_object(self.root / "decomposition_bundle.json")
        atomic_write_json(self.root / "decomposition_bundle.json", {**bundle, "bundle_version": "drift"})
        with self.assertRaisesRegex(DecompositionHandoffError, "hash|current"):
            materialize_approved_decomposition(self.root)


if __name__ == "__main__":
    unittest.main()
