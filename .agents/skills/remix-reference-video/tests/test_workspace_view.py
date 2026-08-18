from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.snapshot_schema_validator import SnapshotSchemaValidator
from remix_reference_video.storage import TaskStorage, atomic_write_json
from remix_reference_video.workspace_media import WorkspaceMediaAuthorizer, WorkspaceMediaError
from remix_reference_video.workspace_view import WorkbenchWorkspaceBuilder


class WorkspaceViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = TaskStorage(self.root)
        self.store.initialize_state(
            {
                "run_id": "run-1",
                "state_revision": 0,
                "active_stage": "gate3_material_selection",
                "active_command": None,
                "gate_status": {
                    "gate1": "approved",
                    "gate2": "approved",
                    "gate3_material_selection": "awaiting_user",
                    "gate3_evidence_closure": "not_ready",
                    "gate4_pre_generation": "not_ready",
                    "gate4_post_generation": "not_ready",
                    "gate5": "not_ready",
                },
                "decisions": [],
                "artifacts": {},
                "blockers": [],
            }
        )
        self.store.update_state(lambda state: state | {"state_revision": 4})
        self.builder = WorkbenchWorkspaceBuilder(self.root)

    def write(self, name: str, value: object) -> None:
        atomic_write_json(self.root / name, value)

    def test_envelope_stage_mapping_and_schema(self) -> None:
        view = self.builder.build("gate3_material_selection")
        self.assertEqual(view["artifact_type"], "workbench_workspace_view")
        self.assertEqual(view["schema_id"], "urn:capcut:remix-reference-video:artifact:workbench-workspace-view")
        self.assertEqual(view["run_id"], "run-1")
        self.assertEqual(view["state_revision"], 1)
        self.assertEqual(view["current_gate"], "gate3_material_selection")
        self.assertEqual(view["summary"]["business_stage"], "素材与证据")
        self.assertEqual(view["process"]["current_stage"], "素材与证据")
        self.assertEqual(view["process"]["stages"][2]["gate_ids"], ["gate3_material_selection", "gate3_evidence_closure"])
        SnapshotSchemaValidator().assert_valid(view, "workbench-workspace-view.schema.json")

    def test_repeated_builds_are_byte_identical_and_ids_are_stable(self) -> None:
        first = self.builder.build("gate1")
        second = self.builder.build("gate1")
        self.assertEqual(json.dumps(first, ensure_ascii=False, sort_keys=True), json.dumps(second, ensure_ascii=False, sort_keys=True))
        self.assertEqual([row["shot_id"] for row in first["storyboard"]["shots"]], [row["shot_id"] for row in second["storyboard"]["shots"]])
        self.assertEqual(first["storyboard"]["shots"], [])

    def test_missing_artifacts_are_not_ready_and_do_not_infer_claims(self) -> None:
        self.write("project_brief.json", {"task_name": "桌垫任务", "product_name": "待确认"})
        view = self.builder.build("gate2")
        self.assertEqual(view["lifecycle_status"], "not_ready")
        self.assertEqual(view["summary"]["product"], "待确认")
        self.assertEqual(view["storyboard"]["elements"], [])
        self.assertIn("待确认", view["decision_context"]["recommendation"])

    def test_projects_real_artifacts_and_uses_gate_timeline_fallbacks(self) -> None:
        self.write("project_brief.json", {"task_name": "桌垫演示", "product_name": "云朵桌垫", "platform": "抖音"})
        self.write(
            "recipe.json",
            {
                "duration_seconds": 8.0,
                "shots": [
                    {"shot_id": "s1", "start_seconds": 0, "end_seconds": 3, "purpose": "开场"},
                    {"shot_id": "s2", "start_seconds": 3, "end_seconds": 8, "purpose": "展示"},
                ],
            },
        )
        self.write("content_baseline.json", {"claims": [{"claim_id": "c1", "text": "防滑"}], "fragments": [{"fragment_id": "fragment01", "narration": "展示产品"}]})
        self.write("mutation_plan.json", {"forbidden_claims": ["治疗"], "allowed_changes": ["copy"]})
        self.write("matches.json", {"fragments": [{"fragment_id": "fragment01", "candidates": [{"asset_id": "a1", "path": "media/source.mp4"}]}]})
        self.write("fragment_plan.json", {"fragments": [{"fragment_id": "fragment01", "approved_broad_range": {"start_seconds": 1, "end_seconds": 4}}]})
        (self.root / "media").mkdir()
        (self.root / "media/source.mp4").write_bytes(b"source")
        view = self.builder.build("gate3_material_selection")
        self.assertEqual(view["summary"]["task"], "桌垫演示")
        self.assertEqual(view["summary"]["product"], "云朵桌垫")
        self.assertEqual(view["storyboard"]["shots"][0]["shot_id"], "shot-s1")
        self.assertEqual(view["storyboard"]["shots"][0]["purpose"], "开场")
        self.assertEqual(view["timeline"]["source"], "approved_broad_range")
        self.assertEqual(view["timeline"]["tracks"][0]["segments"][0]["start_seconds"], 1)
        self.assertEqual(view["storyboard"]["shots"][0]["status"], "ready")

    def test_unclassified_assets_and_media_authorizer_are_explicit(self) -> None:
        self.write("matches.json", {"fragments": []})
        (self.root / "media").mkdir()
        (self.root / "media/unused.mp4").write_bytes(b"unused")
        view = self.builder.build("gate3_material_selection")
        self.assertEqual(view["unclassified_assets"][0]["reason"], "尚未匹配")
        self.assertFalse(view["unclassified_assets"][0]["replacement_eligible"])
        authorizer = WorkspaceMediaAuthorizer(self.root)
        self.assertEqual(authorizer.authorize(view, "media/unused.mp4"), "media/unused.mp4")
        with self.assertRaises(WorkspaceMediaError):
            authorizer.authorize(view, "../outside.mp4")
        with self.assertRaises(WorkspaceMediaError):
            authorizer.authorize(view, "media/missing.mp4")
        (self.root / "media/link.mp4").symlink_to(self.root / "media/unused.mp4")
        with self.assertRaises(WorkspaceMediaError):
            authorizer.authorize(view, "media/link.mp4")


if __name__ == "__main__":
    unittest.main()
