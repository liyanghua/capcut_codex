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

    def test_material_evidence_pause_projects_requirements_without_gate_controls(self) -> None:
        self.store.update_state(
            lambda state: state
            | {
                "active_stage": "collect-material-evidence",
                "gate_status": {**state["gate_status"], "gate3_material_selection": "not_ready"},
                "blockers": [
                    {
                        "category": "manual_classification_required",
                        "requires_user": True,
                        "detail": "需要补充素材业务证据",
                    }
                ],
            }
        )
        self.write(
            "material_evidence_requirements.json",
            {
                "status": "manual_classification_required",
                "input_hashes": {"asset_profiles.json": "a" * 64},
                "requirements": [
                    {
                        "fragment_id": "fragment01",
                        "missing_fields": ["product_type", "semantic_tags", "action_tags"],
                        "eligible_asset_ids": [],
                        "candidate_assets": [
                            {
                                "asset_id": "asset-1",
                                "source_path": "assets/table.jpg",
                                "sha256": "b" * 64,
                                "media_type": "image",
                            }
                        ],
                    }
                ],
            },
        )

        view = self.builder.build("gate3_material_selection")

        evidence = view["decision_context"]["material_evidence"]
        self.assertEqual(view["process"]["current_stage"], "素材证据补充")
        self.assertEqual(evidence["status"], "manual_classification_required")
        self.assertEqual(evidence["requirements"][0]["missing_fields"], ["product_type", "semantic_tags", "action_tags"])
        self.assertFalse(view["decision_context"]["approval_eligibility"])
        self.assertEqual(view["decision_context"]["next_action"], "补充素材业务证据后继续匹配")

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
        self.assertEqual(tracks["picture"][0]["duration_seconds"], 2.5)
        self.assertEqual(view["timeline"]["total_duration_seconds"], 2.5)
        self.assertEqual(view["preview"], {"mode": "final", "media_ref": "remix.mp4", "status": "ready"})

    def test_per_gate_main_preview_resolution_and_fallbacks(self) -> None:
        self.write("project_brief.json", {"task_name": "桌垫演示"})
        self.write("recipe.json", {"reference_video": {"path": "reference-2026-08-16.mp4"}, "shots": []})
        (self.root / "reference-2026-08-16.mp4").write_bytes(b"reference")
        (self.root / "proxy.mp4").write_bytes(b"proxy")

        gate1 = self.builder.build("gate1")
        self.assertEqual(gate1["preview"], {"mode": "reference", "media_ref": "reference-2026-08-16.mp4", "status": "ready"})
        self.assertIn("reference-2026-08-16.mp4", gate1["media_allowlist"])

        gate3 = self.builder.build("gate3_material_selection")
        self.assertEqual(gate3["preview"], {"mode": "proxy", "media_ref": "proxy.mp4", "status": "ready"})

        (self.root / "proxy.mp4").unlink()
        gate4 = self.builder.build("gate4_pre_generation")
        self.assertEqual(gate4["preview"], {"mode": "reference", "media_ref": "reference-2026-08-16.mp4", "status": "ready"})

        (self.root / "reference-2026-08-16.mp4").unlink()
        empty = self.builder.build("gate2")
        self.assertEqual(empty["preview"]["mode"], "empty")
        self.assertIsNone(empty["preview"]["media_ref"])
        self.assertEqual(empty["preview"]["status"], "not_ready")

        gate5 = self.builder.build("gate5")
        self.assertEqual(gate5["preview"]["mode"], "empty")
        self.assertIsNone(gate5["preview"]["media_ref"])

    def test_gate_projection_does_not_leak_future_material_or_voice(self) -> None:
        self.write("recipe.json", {"reference_video": {"path": "reference-2026-08-16.mp4"}, "shots": []})
        self.write("shot_blueprint.json", {"fragments": [{"fragment_id": "fragment01", "narration": "展示产品"}]})
        self.write("content_baseline.json", {"claims": [{"claim_id": "c1", "text": "防水"}], "fragments": [{"fragment_id": "fragment01", "claim_ids": ["c1"]}]})
        self.write("matches.json", {"fragments": [{"fragment_id": "fragment01", "selected_asset_id": "asset-1", "candidates": [{"asset_id": "asset-1", "source_path": "source.mp4"}]}]})
        self.write("fragment_plan.json", {"fragments": [{"fragment_id": "fragment01", "source_path": "source.mp4", "approved_broad_range": {"start_seconds": 0, "end_seconds": 1}}]})
        self.write("script_evidence_matrix.json", {"rows": [{"fragment_id": "fragment01", "voice_text": "透明桌垫防水。"}]})
        self.write("voice/voice_manifest.json", {"segments": [{"fragment_id": "fragment01", "path": "segment.mp3", "measured_duration_seconds": 2}]})
        (self.root / "reference-2026-08-16.mp4").write_bytes(b"reference")
        (self.root / "material/fragment01").mkdir(parents=True)
        (self.root / "material/fragment01/source.mp4").write_bytes(b"material")
        (self.root / "voice").mkdir(exist_ok=True)
        (self.root / "voice/segment.mp3").write_bytes(b"voice")
        (self.root / "proxy.mp4").write_bytes(b"proxy")
        (self.root / "remix.mp4").write_bytes(b"final")

        gate1 = self.builder.build("gate1")

        self.assertEqual([row["shot_id"] for row in gate1["storyboard"]["shots"]], [])
        self.assertEqual(gate1["storyboard"]["audio"], [])
        self.assertNotIn("material/fragment01/source.mp4", gate1["media_allowlist"])
        self.assertNotIn("voice/segment.mp3", gate1["media_allowlist"])
        self.assertNotIn("proxy.mp4", gate1["media_allowlist"])
        self.assertNotIn("remix.mp4", gate1["media_allowlist"])

    def test_rejected_blocked_and_stale_gates_are_not_approvable(self) -> None:
        self.write("recipe.json", {"shots": []})
        self.write("matches.json", {"fragments": []})
        self.write("fragment_plan.json", {"fragments": []})
        for status in ("rejected", "blocked", "stale"):
            self.store.update_state(lambda state, status=status: state | {"gate_status": {**state["gate_status"], "gate3_material_selection": status}})
            view = self.builder.build("gate3_material_selection")
            self.assertFalse(view["decision_context"]["approval_eligibility"], status)
            self.assertEqual(view["process"]["stages"][2]["status"], status)

    def test_gate3_timeline_is_explicitly_source_range_not_output_time(self) -> None:
        self.write("matches.json", {"fragments": []})
        self.write("fragment_plan.json", {"fragments": [{"fragment_id": "fragment01", "approved_broad_range": {"start_seconds": 0, "end_seconds": 14.2}}]})

        view = self.builder.build("gate3_material_selection")

        self.assertEqual(view["timeline"]["timebase"], "source_range")
        self.assertIsNone(view["timeline"]["total_duration_seconds"])

    def test_storyboard_projects_review_frames_elements_and_audio(self) -> None:
        self.write("project_brief.json", {"task_name": "桌垫演示", "product_name": "透明桌垫"})
        self.write(
            "recipe.json",
            {
                "reference_video": {"path": "reference-2026-08-16.mp4"},
                "shots": [
                    {"shot_id": "shot001", "clip_path": "video_clips/shots/shot001.mp4", "keyframe_path": "video_clips/keyframes/shot001.jpg", "start_seconds": 0, "end_seconds": 1},
                ],
            },
        )
        self.write("content_baseline.json", {"claims": [{"claim_id": "c1", "text": "防滑"}], "fragments": [{"fragment_id": "fragment01", "narration": "展示防滑", "claim_ids": ["c1"]}]})
        self.write("matches.json", {"fragments": [{"fragment_id": "fragment01", "selected_asset_id": "asset-1", "candidates": [{"asset_id": "asset-1", "source_path": "source.mp4", "media_type": "video"}]}]})
        self.write("fragment_plan.json", {"fragments": [{"fragment_id": "fragment01", "asset_id": "asset-1", "source_path": "source.mp4", "approved_broad_range": {"start_seconds": 0, "end_seconds": 1}}]})
        self.write("script_evidence_matrix.json", {"rows": [{"fragment_id": "fragment01", "approved_claim_ids": ["c1"], "voice_text": "透明桌垫防滑。"}]})
        self.write("voice/voice_manifest.json", {"segments": [{"fragment_id": "fragment01", "path": "segment-01-fragment01.mp3", "measured_duration_seconds": 2.5}]})
        (self.root / "reference-2026-08-16.mp4").write_bytes(b"reference")
        (self.root / "video_clips/shots").mkdir(parents=True)
        (self.root / "video_clips/keyframes").mkdir(parents=True)
        (self.root / "video_clips/shots/shot001.mp4").write_bytes(b"reference")
        (self.root / "video_clips/keyframes/shot001.jpg").write_bytes(b"frame")
        (self.root / "material/fragment01").mkdir(parents=True)
        (self.root / "material/fragment01/source.mp4").write_bytes(b"source")
        (self.root / "gate3_review_frames").mkdir()
        (self.root / "gate3_review_frames/fragment01.jpg").write_bytes(b"review-frame")
        (self.root / "voice").mkdir(exist_ok=True)
        (self.root / "voice/segment-01-fragment01.mp3").write_bytes(b"voice")

        view = self.builder.build("gate5")

        reference = next(row for row in view["storyboard"]["shots"] if row["shot_id"] == "shot-shot001")
        self.assertEqual(reference["thumbnail_ref"], "video_clips/keyframes/shot001.jpg")
        self.assertEqual(reference["media_type"], "video")
        production = next(row for row in view["storyboard"]["shots"] if row["shot_id"] == "shot-fragment01")
        self.assertEqual(production["thumbnail_ref"], "gate3_review_frames/fragment01.jpg")
        self.assertTrue(production["frame_available"])
        self.assertEqual(production["media_type"], "video")
        self.assertEqual(production["claim_ids"], ["c1"])
        element = next(row for row in view["storyboard"]["elements"] if row["element_id"] == "element-c1")
        self.assertEqual(element["thumbnail_ref"], "gate3_review_frames/fragment01.jpg")
        self.assertEqual(element["related_fragment_ids"], ["fragment01"])
        audio = view["storyboard"]["audio"][0]
        self.assertEqual(audio["media_ref"], "voice/segment-01-fragment01.mp3")
        self.assertEqual(audio["measured_duration_seconds"], 2.5)
        self.assertEqual(audio["status"], "ready")
        self.assertIn("gate3_review_frames/fragment01.jpg", view["media_allowlist"])
        self.assertIn("voice/segment-01-fragment01.mp3", view["media_allowlist"])

    def test_timeline_segments_carry_relations_durations_and_thumbnails(self) -> None:
        self.write("reconstruction_timeline.json", {"fragments": [{"fragment_id": "fragment01", "text": "透明桌垫，防水。", "timeline_start_seconds": 1, "timeline_end_seconds": 3}]})
        self.write("final_validation_report.json", {})
        self.write("render_report.json", {})
        self.write("content_baseline.json", {"fragments": [{"fragment_id": "fragment01", "narration": "展示防水"}]})
        self.write("matches.json", {"fragments": [{"fragment_id": "fragment01", "selected_asset_id": "asset-1", "candidates": [{"asset_id": "asset-1", "source_path": "source.jpg", "media_type": "image"}]}]})
        self.write("fragment_plan.json", {"fragments": [{"fragment_id": "fragment01", "source_path": "source.jpg"}]})
        (self.root / "material/fragment01").mkdir(parents=True)
        (self.root / "material/fragment01/source.jpg").write_bytes(b"source")

        view = self.builder.build("gate5")

        picture = next(track for track in view["timeline"]["tracks"] if track["track_id"] == "picture")["segments"][0]
        self.assertEqual(picture["related_object_id"], "shot-fragment01")
        self.assertEqual(picture["duration_seconds"], 2)
        self.assertEqual(picture["label"], "生产分镜 1")
        self.assertEqual(picture["thumbnail_ref"], "material/fragment01/source.jpg")
        self.assertEqual(view["timeline"]["total_duration_seconds"], 3)
        voice = next(track for track in view["timeline"]["tracks"] if track["track_id"] == "voice")["segments"][0]
        self.assertEqual(voice["related_object_id"], "audio-fragment01")

    def test_media_authorizer_serves_review_frames_and_voice(self) -> None:
        self.write("matches.json", {"fragments": []})
        (self.root / "gate3_review_frames").mkdir()
        (self.root / "gate3_review_frames/fragment01.jpg").write_bytes(b"frame")
        (self.root / "voice").mkdir()
        (self.root / "voice/segment-01-fragment01.mp3").write_bytes(b"voice")
        view = self.builder.build("gate3_material_selection")
        authorizer = WorkspaceMediaAuthorizer(self.root)
        self.assertEqual(authorizer.authorize(view, "gate3_review_frames/fragment01.jpg"), "gate3_review_frames/fragment01.jpg")
        with self.assertRaises(WorkspaceMediaError):
            authorizer.authorize(view, "voice/segment-01-fragment01.mp3")
        gate4 = self.builder.build("gate4_post_generation")
        self.assertEqual(authorizer.authorize(gate4, "voice/segment-01-fragment01.mp3"), "voice/segment-01-fragment01.mp3")
        with self.assertRaises(WorkspaceMediaError):
            authorizer.authorize(view, "gate3_review_frames/missing.jpg")


if __name__ == "__main__":
    unittest.main()
