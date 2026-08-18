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

    def test_projects_nested_v2_brief_and_materialized_selected_assets(self) -> None:
        self.write("project_brief.json", {"project": {"title": "桌垫复刻"}, "product": {"name": "透明桌垫"}, "target": {"platform": "抖音"}})
        self.write("recipe.json", {"shots": [{"shot_id": "shot001", "clip_path": "video_clips/shots/shot001.mp4", "keyframe_path": "video_clips/keyframes/shot001.jpg", "start_seconds": 0, "end_seconds": 1}]})
        self.write("content_baseline.json", {"claims": [], "fragments": [{"fragment_id": "fragment01", "narration": "展示透明质感"}]})
        self.write("matches.json", {"fragments": [{"fragment_id": "fragment01", "selected_asset_id": "asset-1", "candidates": [{"asset_id": "asset-1", "source_path": "source.mp4"}]}]})
        self.write("fragment_plan.json", {"fragments": [{"fragment_id": "fragment01", "asset_id": "asset-1", "source_path": "source.mp4", "approved_broad_range": {"start_seconds": 0, "end_seconds": 1}}]})
        (self.root / "video_clips/shots").mkdir(parents=True)
        (self.root / "video_clips/keyframes").mkdir(parents=True)
        (self.root / "video_clips/shots/shot001.mp4").write_bytes(b"reference")
        (self.root / "video_clips/keyframes/shot001.jpg").write_bytes(b"frame")
        (self.root / "material/fragment01").mkdir(parents=True)
        (self.root / "material/fragment01/source.mp4").write_bytes(b"source")

        view = self.builder.build("gate3_material_selection")

        self.assertEqual(view["summary"]["task"], "桌垫复刻")
        self.assertEqual(view["summary"]["product"], "透明桌垫")
        self.assertEqual(view["summary"]["platform"], "抖音")
        self.assertEqual(view["storyboard"]["shots"][0]["thumbnail_ref"], "video_clips/keyframes/shot001.jpg")
        production = next(row for row in view["storyboard"]["shots"] if row["shot_id"] == "shot-fragment01")
        self.assertEqual(production["media_ref"], "material/fragment01/source.mp4")
        self.assertEqual(production["purpose"], "展示透明质感")
        self.assertNotIn("material/fragment01/source.mp4", [row["media_ref"] for row in view["unclassified_assets"]])

    def test_gate5_projects_real_voice_and_subtitle_tracks(self) -> None:
        self.write("reconstruction_timeline.json", {"fragments": [{"fragment_id": "fragment01", "text": "透明桌垫，防水。", "timeline_start_seconds": 0, "timeline_end_seconds": 2.5}]})
        self.write("final_validation_report.json", {})
        self.write("render_report.json", {})
        (self.root / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:02,500\n透明桌垫，防水。\n", encoding="utf-8")
        (self.root / "remix.mp4").write_bytes(b"video")

        view = self.builder.build("gate5")

        tracks = {row["track_id"]: row["segments"] for row in view["timeline"]["tracks"]}
        self.assertEqual(tracks["voice"][0]["label"], "透明桌垫，防水。")
        self.assertEqual(tracks["subtitles"][0]["start_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
