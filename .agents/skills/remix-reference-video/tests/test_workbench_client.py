from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.storage import TaskStorage, atomic_write_json
from remix_reference_video.workspace_view import WorkbenchWorkspaceBuilder

_SCRIPT_DIR = Path(__file__).resolve().parent
_HARNESS = _SCRIPT_DIR / "client_workbench_harness.js"
_CLIENT_JS = _SCRIPT_DIR.parent / "src/remix_reference_video/static/review_workbench.js"
_PROJECT_HARNESS = _SCRIPT_DIR / "client_project_initialization_harness.js"
_PROJECT_CLIENT_JS = _SCRIPT_DIR.parent / "src/remix_reference_video/static/project_initialization.js"


class WorkbenchClientContractTests(unittest.TestCase):
    def test_client_never_uses_full_page_reload(self) -> None:
        self.assertNotIn("location.reload", _CLIENT_JS.read_text(encoding="utf-8"))

    def test_project_initialization_picker_and_draft_handlers_execute(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("node runtime is unavailable")
        result = subprocess.run(
            [node, str(_PROJECT_HARNESS)], capture_output=True, text=True,
            env={**os.environ, "PROJECT_INITIALIZATION_JS": str(_PROJECT_CLIENT_JS)}, timeout=60,
        )
        self.assertEqual(result.returncode, 0, f"{result.stdout}\n{result.stderr}")
        self.assertIn("project initialization client contract OK", result.stdout)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = TaskStorage(self.root)
        self.store.initialize_state(
            {
                "run_id": "run-1",
                "state_revision": 0,
                "active_stage": "build-gate5-package",
                "active_command": None,
                "gate_status": {
                    "gate1": "approved",
                    "gate2": "approved",
                    "gate3": "approved",
                    "gate3_material_selection": "approved",
                    "gate3_evidence_closure": "approved",
                    "gate4": "approved",
                    "gate4_pre_generation": "approved",
                    "gate4_post_generation": "approved",
                    "gate5": "awaiting_user",
                },
                "decisions": [],
                "artifacts": {},
                "blockers": [],
            }
        )
        atomic_write_json(self.root / "project_brief.json", {"task_name": "桌垫演示", "product_name": "透明桌垫", "platform": "抖音"})
        atomic_write_json(
            self.root / "recipe.json",
            {
                "reference_video": {"path": "reference-2026-08-16.mp4"},
                "shots": [{"shot_id": "shot001", "clip_path": "video_clips/shots/shot001.mp4", "keyframe_path": "video_clips/keyframes/shot001.jpg", "start_seconds": 0, "end_seconds": 1}],
            },
        )
        atomic_write_json(self.root / "content_baseline.json", {"claims": [{"claim_id": "c1", "text": "防滑"}], "fragments": [{"fragment_id": "fragment01", "narration": "展示防滑", "claim_ids": ["c1"]}]})
        atomic_write_json(self.root / "matches.json", {"fragments": [{"fragment_id": "fragment01", "selected_asset_id": "asset-1", "candidates": [{"asset_id": "asset-1", "source_path": "source.jpg", "media_type": "image"}]}]})
        atomic_write_json(self.root / "fragment_plan.json", {"fragments": [{"fragment_id": "fragment01", "asset_id": "asset-1", "source_path": "source.jpg", "approved_broad_range": {"start_seconds": 0, "end_seconds": 3}}]})
        atomic_write_json(self.root / "script_evidence_matrix.json", {"rows": [{"fragment_id": "fragment01", "approved_claim_ids": ["c1"], "voice_text": "透明桌垫防滑。"}]})
        atomic_write_json(self.root / "reconstruction_timeline.json", {"fragments": [{"fragment_id": "fragment01", "text": "透明桌垫防滑。", "timeline_start_seconds": 0, "timeline_end_seconds": 3}]})
        atomic_write_json(self.root / "final_validation_report.json", {"status": "passed", "hard_gate_checks": {"duration": "passed"}})
        atomic_write_json(self.root / "render_report.json", {"status": "passed"})
        atomic_write_json(
            self.root / "approved_production_script.json",
            {"lifecycle_status": "approved", "lines": [{"fragment_id": "fragment01", "line_id": "line01", "text": "透明桌垫防滑。"}], "tts_settings": {"provider": "doubao-v3", "speaker": "zh_female", "speed": 1.0}},
        )
        atomic_write_json(
            self.root / "voice_preflight.json",
            {"preflight_status": "passed", "blocked_fragment_ids": [], "fragments": [{"fragment_id": "fragment01", "preflight_status": "passed", "voice_duration_estimate_seconds": 2.5, "visual_duration_budget_seconds": 3.0, "voice_duration_margin_seconds": 0.5}]},
        )
        atomic_write_json(self.root / "voice/voice_manifest.json", {"segments": [{"fragment_id": "fragment01", "path": "segment-01-fragment01.mp3", "measured_duration_seconds": 2.5}]})
        (self.root / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:03,000\n透明桌垫防滑。\n", encoding="utf-8")
        for relative in (
            "reference-2026-08-16.mp4",
            "remix.mp4",
            "proxy.mp4",
            "material/fragment01/source.jpg",
            "gate3_review_frames/fragment01.jpg",
            "voice/segment-01-fragment01.mp3",
            "video_clips/shots/shot001.mp4",
            "video_clips/keyframes/shot001.jpg",
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
        self.store.update_state(lambda state: state | {"state_revision": 9})

    def _run_harness(self, view: dict[str, object], *, stale_review: bool = False) -> str:
        node = shutil.which("node")
        if not node:
            self.skipTest("node runtime is unavailable")
        fixtures = Path(self.temp.name) / "fixtures"
        fixtures.mkdir()
        (fixtures / "workspace.json").write_text(json.dumps(view, ensure_ascii=False), encoding="utf-8")
        refreshed = json.loads(json.dumps(view))
        refreshed["state_revision"] = int(view.get("state_revision", 0)) + 1
        refreshed["decision_context"] = {**(refreshed.get("decision_context") or {}), "question": "刷新后的判断问题"}
        (fixtures / "workspace2.json").write_text(json.dumps(refreshed, ensure_ascii=False), encoding="utf-8")
        (fixtures / "review.json").write_text(json.dumps({"impact_context": {"decision_scope_ids": []}}), encoding="utf-8")
        (fixtures / "session.json").write_text(json.dumps({"session_id": "s1", "review_identity": {"review_package_hash": "h", "state_revision": 9}}), encoding="utf-8")
        env = {**os.environ, "WORKBENCH_FIXTURES": str(fixtures), "WORKBENCH_JS": str(_CLIENT_JS)}
        if stale_review:
            env["WORKBENCH_REVIEW_STALE"] = "1"
        result = subprocess.run([node, str(_HARNESS)], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, f"{result.stdout}\n{result.stderr}")
        return result.stdout

    def test_client_contract_gate5(self) -> None:
        view = WorkbenchWorkspaceBuilder(self.root).build("gate5")
        self.assertIn("client contract OK", self._run_harness(view))

    def test_client_contract_gate4(self) -> None:
        self.store.update_state(lambda state: state | {"gate_status": {**state["gate_status"], "gate4_pre_generation": "awaiting_user", "gate5": "not_ready"}})
        view = WorkbenchWorkspaceBuilder(self.root).build("gate4_pre_generation")
        self.assertIn("client contract OK", self._run_harness(view))

    def test_client_contract_gate1_pending_states(self) -> None:
        self.store.update_state(lambda state: state | {"gate_status": {**state["gate_status"], "gate1": "awaiting_user"}})
        view = WorkbenchWorkspaceBuilder(self.root).build("gate1")
        self.assertEqual(view["storyboard"]["section_states"]["elements"], "pending_gate2")
        self.assertIn("client contract OK", self._run_harness(view))

    def test_stale_review_package_keeps_workspace_visible_in_read_only_mode(self) -> None:
        view = WorkbenchWorkspaceBuilder(self.root).build("gate5")
        self.assertIn("client contract OK", self._run_harness(view, stale_review=True))


if __name__ == "__main__":
    unittest.main()
