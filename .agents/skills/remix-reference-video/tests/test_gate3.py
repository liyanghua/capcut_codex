from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.adapters.gate3 import (
    Gate3Adapter,
    Gate3Error,
    gate3_stale_projection,
)
from remix_reference_video.approvals import ApprovalService
from remix_reference_video.storage import TaskStorage, atomic_write_json, read_json_object


class Gate3AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.store = TaskStorage(self.root)
        self.store.initialize_state(
            {
                "execution_mode": "track-b-production",
                "run_id": "run-1",
                "state_revision": 0,
                "active_stage": "retrieval",
                "active_command": None,
                "stage_status": {},
                "gate_status": {
                    "gate1": "approved",
                    "gate2": "approved",
                    "gate3_material_selection": "awaiting_user",
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
        self.adapter = Gate3Adapter()
        self.candidate = self.root / "material_selection_candidate.json"
        atomic_write_json(
            self.candidate,
            {
                "artifact_type": "material_selection_candidate",
                "selections": [
                    {
                        "fragment_id": "fragment01",
                        "asset_id": "asset-a",
                        "source_id": "source-a",
                        "source_path": "clip.mp4",
                        "sha256": "a" * 64,
                        "overlay_policy": "cover",
                        "approved_broad_range": {
                            "start_seconds": 0.5,
                            "end_seconds": 3.0,
                        },
                        "available_source_range": {
                            "start_seconds": 0.0,
                            "end_seconds": 4.0,
                        },
                    }
                ],
            },
        )

    @staticmethod
    def sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def approve_selection(self, strategy: dict[str, object]) -> dict[str, object]:
        package = self.adapter.build_material_selection_package(
            candidate_path=self.candidate,
            run_id="run-1",
            state_revision=self.store.read_state()["state_revision"],
            created_at="2026-08-15T12:00:00Z",
        )
        package_path = self.root / "gate_review_packages/gate3_material_selection.json"
        atomic_write_json(package_path, package)
        decision = self.root / "decision.json"
        atomic_write_json(
            decision,
            {
                "decision": "approved",
                "scope_type": "fragment_set",
                "scope_ids": ["fragment01"],
                "strategy": strategy,
            },
        )
        return ApprovalService(self.store).approve(
            gate_id="gate3_material_selection",
            review_package_hash=self.sha256(package_path),
            decision_file=decision,
            actor="owner",
        )

    def test_current_hash_approval_freezes_extended_broad_range(self) -> None:
        approval = self.approve_selection(
            {
                "range_overrides": {
                    "fragment01": {"start_seconds": 0.5, "end_seconds": 3.5}
                }
            }
        )
        plan = self.adapter.freeze_fragment_plan(
            candidate_path=self.candidate,
            approval_record=approval,
        )

        self.assertEqual(plan["artifact_type"], "fragment_plan")
        self.assertEqual(plan["fragments"][0]["source_path"], "clip.mp4")
        self.assertEqual(plan["fragments"][0]["media_type"], "video")
        self.assertEqual(
            plan["fragments"][0]["visual_duration_budget_seconds"], 3.0
        )
        self.assertEqual(
            plan["fragments"][0]["approved_broad_range"]["end_seconds"], 3.5
        )
        atomic_write_json(self.candidate, {"artifact_type": "material_selection_candidate", "selections": []})
        with self.assertRaisesRegex(Gate3Error, "current candidate hash"):
            self.adapter.freeze_fragment_plan(
                candidate_path=self.candidate,
                approval_record=approval,
            )

    def test_range_extension_cannot_exceed_available_source(self) -> None:
        approval = self.approve_selection(
            {
                "range_overrides": {
                    "fragment01": {"start_seconds": 0.5, "end_seconds": 4.5}
                }
            }
        )
        with self.assertRaisesRegex(Gate3Error, "available source range"):
            self.adapter.freeze_fragment_plan(
                candidate_path=self.candidate,
                approval_record=approval,
            )

    def test_image_selection_freezes_without_temporal_source_range(self) -> None:
        candidate = read_json_object(self.candidate)
        candidate["selections"][0]["source_path"] = "detail.jpg"
        atomic_write_json(self.candidate, candidate)
        approval = self.approve_selection({})

        plan = self.adapter.freeze_fragment_plan(
            candidate_path=self.candidate,
            approval_record=approval,
        )

        self.assertEqual(
            plan["fragments"][0]["approved_broad_range"],
            {"start_seconds": None, "end_seconds": None},
        )
        self.assertEqual(plan["fragments"][0]["media_type"], "image")
        self.assertIsNone(
            plan["fragments"][0]["visual_duration_budget_seconds"]
        )

    def test_evidence_closure_and_summary_remain_separate(self) -> None:
        approval = self.approve_selection({})
        plan = self.adapter.freeze_fragment_plan(
            candidate_path=self.candidate,
            approval_record=approval,
        )
        baseline = self.root / "content_baseline.json"
        fragment_plan = self.root / "fragment_plan.json"
        atomic_write_json(
            baseline,
            {
                "artifact_type": "content_baseline",
                "claims": [{"claim_id": "clean", "text": "可擦净"}],
                "fragments": [
                    {"fragment_id": "fragment01", "narration": "可擦净", "claim_ids": ["clean"]}
                ],
            },
        )
        atomic_write_json(fragment_plan, plan)
        matrix = self.adapter.validate_script_evidence(
            content_baseline_path=baseline,
            fragment_plan_path=fragment_plan,
            evidence_rows=[
                {
                    "fragment_id": "fragment01",
                    "voice_text": "可擦净",
                    "approved_claim_ids": ["clean"],
                    "closure_decision": "closed",
                }
            ],
        )
        self.assertEqual(matrix["lifecycle_status"], "awaiting_user")
        matrix_path = self.root / "script_evidence_matrix.json"
        atomic_write_json(matrix_path, matrix)
        evidence_package = self.adapter.build_evidence_package(
            evidence_matrix_path=matrix_path,
            run_id="run-1",
            state_revision=self.store.read_state()["state_revision"],
            created_at="2026-08-15T12:01:00Z",
        )
        evidence_package_path = self.root / "gate_review_packages/gate3_evidence_closure.json"
        atomic_write_json(evidence_package_path, evidence_package)
        decision = self.root / "evidence-decision.json"
        atomic_write_json(
            decision,
            {
                "decision": "approved",
                "scope_type": "artifact_set",
                "scope_ids": ["script_evidence_matrix.json"],
                "strategy": {},
            },
        )
        ApprovalService(self.store).approve(
            gate_id="gate3_evidence_closure",
            review_package_hash=self.sha256(evidence_package_path),
            decision_file=decision,
            actor="owner",
        )
        self.assertEqual(self.store.read_state()["gate_status"]["gate3"], "approved")
        self.assertEqual(
            self.adapter.summarize_gate3(
                {
                    "gate3_material_selection": "approved",
                    "gate3_evidence_closure": "awaiting_user",
                }
            ),
            "awaiting_user",
        )
        self.assertEqual(
            self.adapter.summarize_gate3(
                {
                    "gate3_material_selection": "approved",
                    "gate3_evidence_closure": "approved",
                }
            ),
            "approved",
        )

    def test_material_or_overlay_change_stales_both_substates_and_structure_returns_gate2(self) -> None:
        stale = gate3_stale_projection(
            change_type="overlay",
            affected_asset_ids={"asset-a"},
            selected_asset_ids={"asset-a", "asset-b"},
        )
        self.assertEqual(stale["gate_status"]["gate3_material_selection"], "stale")
        self.assertEqual(stale["gate_status"]["gate3_evidence_closure"], "stale")
        self.assertEqual(stale["reusable_asset_ids"], ["asset-b"])
        approval = self.approve_selection({"request_merge": ["fragment01"]})
        with self.assertRaisesRegex(Gate3Error, "return to Gate 2"):
            self.adapter.freeze_fragment_plan(
                candidate_path=self.candidate,
                approval_record=approval,
            )


if __name__ == "__main__":
    unittest.main()
