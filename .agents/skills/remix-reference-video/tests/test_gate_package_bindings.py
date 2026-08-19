from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.approvals import ApprovalError, ApprovalService
from remix_reference_video.storage import TaskStorage, atomic_write_json, read_json_object


class CreativeGatePackageBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = TaskStorage(self.root)
        self.store.initialize_state(
            {
                "execution_mode": "track-b-production",
                "run_id": "creative-run",
                "state_revision": 0,
                "active_stage": "performance_proven_video",
                "stage_status": {},
                "gate_status": {
                    "gate1": "awaiting_user",
                    "gate2": "not_ready",
                    "gate3_material_selection": "not_ready",
                    "gate3_evidence_closure": "not_ready",
                    "gate3": "not_ready",
                    "gate4_pre_generation": "not_ready",
                    "gate4_post_generation": "not_ready",
                    "gate4": "not_ready",
                    "gate5": "not_ready",
                },
                "decisions": [],
                "artifacts": {},
                "blockers": [],
                "cache_summary": {},
            }
        )
        atomic_write_json(self.root / "g_b_frozen_input_snapshot.json", {"creative_contract_version": "creative_contract_v1"})
        self.service = ApprovalService(self.store)

    @staticmethod
    def _sha(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def _decision(self, strategy: dict[str, object]) -> Path:
        path = self.root / "decision.json"
        atomic_write_json(path, {
            "decision": "approved",
            "scope_type": "artifact_set",
            "scope_ids": ["creative"],
            "strategy": strategy,
        })
        return path

    def _package(self, gate: str, paths: list[str], **extra: object) -> str:
        hashes: dict[str, str] = {}
        for relative in paths:
            hashes[relative] = self._sha(self.root / relative)
        package = {
            "run_id": "creative-run",
            "gate_id": gate,
            "created_at": "2026-08-19T09:00:00Z",
            "state_revision": self.store.read_state()["state_revision"],
            "input_hashes": hashes,
            **extra,
        }
        path = self.root / "gate_review_packages" / f"{gate}.json"
        atomic_write_json(path, package)
        return self._sha(path)

    def _approve(self, gate: str, strategy: dict[str, object], paths: list[str], **extra: object) -> dict[str, object]:
        digest = self._package(gate, paths, **extra)
        return self.service.approve(
            gate_id=gate,
            review_package_hash=digest,
            decision_file=self._decision(strategy),
            actor="owner",
        )

    def test_gate1_binds_one_decomposition_to_current_bundle(self) -> None:
        atomic_write_json(self.root / "recipe.json", {"artifact_type": "recipe"})
        atomic_write_json(self.root / "decomposition_bundle.json", {
            "artifact_type": "decomposition_bundle",
            "candidates": [{"decomposition_id": "decomp-a"}],
        })
        result = self._approve("gate1", {"selected_decomposition_id": "decomp-a"}, ["recipe.json", "decomposition_bundle.json"])
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(result["strategy"]["selected_decomposition_id"], "decomp-a")

    def test_gate1_rejects_unknown_or_multiple_selection(self) -> None:
        atomic_write_json(self.root / "recipe.json", {"artifact_type": "recipe"})
        atomic_write_json(self.root / "decomposition_bundle.json", {"artifact_type": "decomposition_bundle", "candidates": [{"decomposition_id": "decomp-a"}]})
        with self.assertRaisesRegex(ApprovalError, "decomposition"):
            self._approve("gate1", {"selected_decomposition_id": "missing"}, ["recipe.json", "decomposition_bundle.json"])
        with self.assertRaisesRegex(ApprovalError, "selected_decomposition_id"):
            self._approve("gate1", {"selected_decomposition_id": ["decomp-a"]}, ["recipe.json", "decomposition_bundle.json"])

    def test_gate2_binds_strategy_and_rejects_stale_bundle_hash(self) -> None:
        self.store.update_state(lambda state: state | {"gate_status": state["gate_status"] | {"gate1": "approved", "gate2": "awaiting_user"}})
        for name, value in (("content_baseline.json", {"artifact_type": "content_baseline"}), ("mutation_plan.json", {"artifact_type": "mutation_plan"}), ("creative_objective.json", {"artifact_type": "creative_objective"}), ("remix_strategy_candidates.json", {"artifact_type": "remix_strategy_candidates", "candidates": [{"strategy_id": "balanced_remix_v1", "status": "passed"}]}), ("coverage_precheck.json", {"artifact_type": "coverage_precheck"})):
            atomic_write_json(self.root / name, value)
        result = self._approve("gate2", {"selected_remix_strategy_id": "balanced_remix_v1"}, ["content_baseline.json", "mutation_plan.json", "creative_objective.json", "remix_strategy_candidates.json", "coverage_precheck.json"])
        self.assertEqual(result["decision"], "approved")

        candidates = self.root / "remix_strategy_candidates.json"
        self.store.update_state(lambda state: state | {"gate_status": state["gate_status"] | {"gate2": "awaiting_user"}})
        digest = self._package("gate2", ["content_baseline.json", "mutation_plan.json", "creative_objective.json", "remix_strategy_candidates.json", "coverage_precheck.json"])
        atomic_write_json(candidates, read_json_object(candidates) | {"revision": 2})
        with self.assertRaisesRegex(ApprovalError, "hash mismatch"):
            self.service.approve(gate_id="gate2", review_package_hash=digest, decision_file=self._decision({"selected_remix_strategy_id": "balanced_remix_v1"}), actor="owner")

    def test_gate4_requires_passed_script_candidate_bound_to_report(self) -> None:
        self.store.update_state(lambda state: state | {"gate_status": state["gate_status"] | {"gate1": "approved", "gate2": "approved", "gate3_material_selection": "approved", "gate3_evidence_closure": "approved", "gate3": "approved", "gate4_pre_generation": "awaiting_user"}})
        atomic_write_json(self.root / "script_candidates.json", {"artifact_type": "script_candidates", "candidates": [{"script_candidate_id": "script-a", "status": "candidate"}]})
        atomic_write_json(self.root / "script_candidate_validation_report.json", {"artifact_type": "script_candidate_validation_report", "candidates": [{"script_candidate_id": "script-a", "status": "passed"}]})
        atomic_write_json(self.root / "production_script_candidate.json", {"artifact_type": "production_script_candidate", "lines": []})
        atomic_write_json(self.root / "voice_preflight.json", {"artifact_type": "voice_preflight", "preflight_status": "passed", "speed": 1.0, "fragments": []})
        result = self._approve("gate4_pre_generation", {"selected_script_candidate_id": "script-a", "tts_settings": {"provider": "doubao", "speed_ratio": 1.0}}, ["script_candidates.json", "script_candidate_validation_report.json", "production_script_candidate.json", "voice_preflight.json"])
        self.assertEqual(result["decision"], "approved")

        self.store.update_state(lambda state: state | {"gate_status": state["gate_status"] | {"gate4_pre_generation": "awaiting_user"}})
        report = self.root / "script_candidate_validation_report.json"
        atomic_write_json(report, {"artifact_type": "script_candidate_validation_report", "candidates": [{"script_candidate_id": "script-a", "status": "blocked"}]})
        with self.assertRaisesRegex(ApprovalError, "passed"):
            self._approve("gate4_pre_generation", {"selected_script_candidate_id": "script-a", "tts_settings": {"provider": "doubao", "speed_ratio": 1.0}}, ["script_candidates.json", "script_candidate_validation_report.json", "production_script_candidate.json", "voice_preflight.json"])

    def test_legacy_gate4_does_not_require_creative_selection(self) -> None:
        (self.root / "g_b_frozen_input_snapshot.json").unlink()
        self.store.update_state(lambda state: state | {"gate_status": state["gate_status"] | {"gate1": "approved", "gate2": "approved", "gate3_material_selection": "approved", "gate3_evidence_closure": "approved", "gate3": "approved", "gate4_pre_generation": "awaiting_user"}})
        atomic_write_json(self.root / "production_script_candidate.json", {"artifact_type": "production_script_candidate", "lines": []})
        atomic_write_json(self.root / "voice_preflight.json", {"artifact_type": "voice_preflight", "preflight_status": "passed", "speed": 1.0, "fragments": []})
        result = self._approve("gate4_pre_generation", {"tts_settings": {"provider": "doubao", "speed_ratio": 1.0}}, ["production_script_candidate.json", "voice_preflight.json"])
        self.assertEqual(result["decision"], "approved")


if __name__ == "__main__":
    unittest.main()
