from __future__ import annotations

import importlib.util
import hashlib
import re
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from remix_reference_video.api import ProgressProjector, create_app
from remix_reference_video.material_evidence import build_material_evidence_requirements
from remix_reference_video.run_registry import RunRegistry
from remix_reference_video.storage import TaskStorage, atomic_write_json, read_json_object
from tests.frozen_run_fixture import write_frozen_run_fixture


class ProgressApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.workspace = Path(self._temporary.name).resolve()
        self.task = self.workspace / "task-1"
        self.task.mkdir()
        self.store = TaskStorage(self.task)
        self.store.initialize_state(
            {
                "execution_mode": "track-b-production",
                "run_id": "run-1",
                "state_revision": 0,
                "active_stage": "retrieval",
                "active_command": None,
                "stage_status": {"match-assets": "running"},
                "gate_status": {"gate1":"approved","gate2":"approved","gate3_material_selection":"awaiting_user","gate3_evidence_closure":"not_ready","gate3":"awaiting_user","gate4_pre_generation":"not_ready","gate4_post_generation":"not_ready","gate4":"not_ready","gate5":"not_ready"},
                "decisions": [{"actor": "secret@example.test", "note": "private"}],
                "artifacts": {
                    "remix.mp4": {"path": "remix.mp4", "sha256": "a" * 64},
                    "internal": {"path": ".transactions/private.json", "sha256": "b" * 64},
                },
                "blockers": [],
                "cache_summary": {},
            }
        )
        (self.task / "remix.mp4").write_bytes(b"video")
        write_frozen_run_fixture(self.task, pair_role="cold")
        atomic_write_json(self.task / "gate_review_packages/gate3_material_selection.json", {"gate_id":"gate3_material_selection","run_id":"run-1","state_revision":0,"created_at":"2026-08-17T10:00:00Z","input_hashes":{}})
        atomic_write_json(self.task / "fragment_plan.json", {"fragments":[{"fragment_id":"fragment01","approved_broad_range":{"start_seconds":0.0,"end_seconds":2.0}}]})
        atomic_write_json(self.task / "matches.json", {"fragments":[{"fragment_id":"fragment01","candidates":[{"candidate_id":"c1","source_sha256":"a"*64}]}]})
        atomic_write_json(self.task / "material_selection_candidate.json", {"artifact_type":"material_selection_candidate","selections":[]})
        atomic_write_json(self.task / "stage_inputs/build-material-selection-package.json", {"artifact_type":"stage_input","schema_id":"urn:capcut:remix-reference-video:artifact:stage-input","schema_version":"1.0.0","contract_version":"2.0.0-alpha.1","skill_version":"2.0.0-alpha.1","stage_id":"build-material-selection-package","producer":"test","created_at":"2026-08-17T10:00:00Z","lifecycle_status":"awaiting_user","input_hashes":{},"payload":{"overlay_decisions":{"fragment01":"no_action"}}})
        (self.task / "gate3_review_contact_sheet.jpg").write_bytes(b"0123456789")
        self.store.append_event({"event_type": "stage.started"}, state_revision=0)
        self.store.append_event({"event_type": "stage.progress"}, state_revision=0)
        RunRegistry(self.workspace).register(self.task)
        self.projector = ProgressProjector(self.workspace)

    def test_progress_view_is_redacted_and_revision_etagged(self) -> None:
        before = (self.task / "pipeline_state.json").read_bytes()
        view = self.projector.task_detail("task-1")
        self.assertEqual(view["etag"], '"revision-0"')
        self.assertEqual(view["progress"]["current_stage"], "素材匹配与证据")
        self.assertNotIn("decisions", str(view))
        self.assertNotIn("secret@example.test", str(view))
        self.assertEqual((self.task / "pipeline_state.json").read_bytes(), before)

    def test_artifact_metadata_uses_allowlist_without_exposing_paths(self) -> None:
        metadata = self.projector.artifact_metadata("task-1", "remix.mp4")
        self.assertEqual(metadata["name"], "remix.mp4")
        self.assertEqual(metadata["size_bytes"], 5)
        self.assertNotIn("path", metadata)
        with self.assertRaises(KeyError):
            self.projector.artifact_metadata("task-1", "internal")

    def test_sse_reconnect_deduplicates_and_starts_after_last_event_id(self) -> None:
        notices = self.projector.revision_notices("task-1", last_event_id="1")
        self.assertEqual([item["id"] for item in notices], ["2"])
        self.assertEqual(notices[0]["event"], "revision")
        self.assertEqual(len(self.projector.revision_notices("task-1", last_event_id="2")), 0)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI optional extra unavailable")
    def test_workbench_review_session_events_and_page_routes(self) -> None:
        from fastapi.testclient import TestClient

        with patch.dict("os.environ", {"WORKBENCH_UI_MODE": "workspace"}, clear=False):
            client = TestClient(create_app(self.workspace, actor="operator-a"))
        review = client.get("/api/v1/runs/run-1/review")
        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.json()["gate_id"], "gate3_material_selection")
        self.assertEqual(review.headers["etag"], f'"review-{review.json()["bound_package_sha256"]}"')
        opened = client.post("/api/v1/runs/run-1/review-session", json={"gate_id":"gate3_material_selection"})
        self.assertEqual(opened.status_code, 200)
        session_id = opened.json()["session_id"]
        event = client.post(f"/api/v1/runs/run-1/review-session/events", json={"session_id":session_id,"event_type":"review.evidence_interaction","payload":{"evidence_id":"matches.json"},"actor":"forged"})
        self.assertEqual(event.status_code, 200)
        self.assertEqual(self.store.read_events()[-1]["actor"], "operator-a")
        page = client.get("/workbench/runs/run-1")
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="preview-stage"', page.text)
        self.assertIn('id="decision-assistant"', page.text)
        self.assertIn('id="review-timeline"', page.text)
        self.assertIn("data-action=\"approve\"", page.text)
        self.assertIn("data-action=\"reject\"", page.text)
        self.assertIn("data-action=\"request_changes\"", page.text)
        self.assertIn("id=\"change-target\"", page.text)
        script = client.get("/static/review_workbench.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("new EventSource", script.text)
        self.assertNotIn('addEventListener("revision", () => location.reload())', script.text)
        self.assertIn('const current = await api("/workspace")', script.text)
        self.assertIn("state.reloadPending", script.text)
        self.assertIn("<video", script.text)
        self.assertIn("<audio", script.text)
        self.assertIn("<img", script.text)
        self.assertEqual(client.get("/static/review_workbench.js").status_code, 200)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI optional extra unavailable")
    def test_workspace_snapshot_has_etag_and_304(self) -> None:
        from fastapi.testclient import TestClient

        client = TestClient(create_app(self.workspace, actor="operator-a"))
        response = client.get("/api/v1/runs/run-1/workspace")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["artifact_type"], "workbench_workspace_view")
        self.assertEqual(payload["current_gate"], "gate3_material_selection")
        self.assertIn("storyboard", payload)
        self.assertIn("media_allowlist", payload)
        self.assertEqual(client.get("/api/v1/runs/run-1/workspace", headers={"If-None-Match":response.headers["etag"]}).status_code, 304)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI optional extra unavailable")
    def test_invalid_ui_mode_fails_closed_to_legacy(self) -> None:
        from fastapi.testclient import TestClient

        with patch.dict("os.environ", {"WORKBENCH_UI_MODE": "unexpected"}, clear=False):
            client = TestClient(create_app(self.workspace, actor="operator-a"))
        page = client.get("/workbench/runs/run-1")
        self.assertIn("视频审核工作台", page.text)
        self.assertNotIn('id="preview-stage"', page.text)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI optional extra unavailable")
    def test_media_range_allowlist_etag_and_416(self) -> None:
        from fastapi.testclient import TestClient

        client = TestClient(create_app(self.workspace, actor="operator-a"))
        response = client.get("/api/v1/runs/run-1/media/gate3_review_contact_sheet.jpg", headers={"Range":"bytes=2-5"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b"2345")
        self.assertEqual(response.headers["content-range"], "bytes 2-5/10")
        etag = response.headers["etag"]
        self.assertEqual(client.get("/api/v1/runs/run-1/media/gate3_review_contact_sheet.jpg", headers={"If-None-Match":etag}).status_code, 304)
        self.assertEqual(client.get("/api/v1/runs/run-1/media/gate3_review_contact_sheet.jpg", headers={"Range":"bytes=20-30"}).status_code, 416)
        self.assertEqual(client.get("/api/v1/runs/run-1/media/pipeline_state.json").status_code, 404)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI optional extra unavailable")
    def test_source_media_requires_profile_and_frozen_snapshot_hash_match(self) -> None:
        from fastapi.testclient import TestClient

        source = self.task / "fixture-assets" / "asset.mp4"
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        atomic_write_json(self.task / "asset_profiles.json", {
            "artifact_type": "asset_profiles",
            "asset_profiles": [{
                "asset_id": "asset-source", "source_path": "asset.mp4",
                "sha256": source_hash, "media_type": "video",
            }],
        })
        frozen = read_json_object(self.task / "g_b_frozen_input_snapshot.json")
        atomic_write_json(self.task / "g_b_frozen_input_snapshot.json", {
            **frozen,
            "asset_profiles_sha256": hashlib.sha256((self.task / "asset_profiles.json").read_bytes()).hexdigest(),
        })
        registry = RunRegistry(self.workspace)
        registry.repair("run-1", self.task, expected_registry_revision=registry._read()["registry_revision"], actor="operator-a")
        client = TestClient(create_app(self.workspace, actor="operator-a"))

        response = client.get("/api/v1/runs/run-1/source-media/asset-source", headers={"Range": "bytes=0-4"})

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b"asset")
        self.assertEqual(client.get("/api/v1/runs/run-1/source-media/unknown").status_code, 404)
        source.write_bytes(b"changed")
        self.assertEqual(client.get("/api/v1/runs/run-1/source-media/asset-source").status_code, 409)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI optional extra unavailable")
    def test_change_preview_apply_and_sse_resume(self) -> None:
        from fastapi.testclient import TestClient

        client = TestClient(create_app(self.workspace, actor="operator-a"))
        opened = client.post("/api/v1/runs/run-1/review-session", json={"gate_id":"gate3_material_selection"}).json()
        request = {"change_type":"range","scope_ids":["fragment01"],"payload":{"fragment_id":"fragment01","start_seconds":0.25,"end_seconds":1.75},"reason":"收窄范围"}
        preview = client.post("/api/v1/runs/run-1/gates/gate3_material_selection/changes/preview", json={"session_id":opened["session_id"],"request":request})
        self.assertEqual(preview.status_code, 200)
        applied = client.post("/api/v1/runs/run-1/gates/gate3_material_selection/changes", json={"session_id":opened["session_id"],"request":request,"preview_hash":preview.json()["preview_hash"],"idempotency_key":"api-change-1"})
        self.assertEqual(applied.status_code, 200)
        self.assertTrue(Path(applied.json()["job_path"]).is_file())
        events = client.get("/api/v1/runs/run-1/events", headers={"Last-Event-ID":"2"})
        self.assertEqual(events.status_code, 200)
        self.assertIn("retry: 15000", events.text)
        self.assertIn("event: revision", events.text)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI optional extra unavailable")
    def test_decision_conflict_returns_refresh_contract(self) -> None:
        from fastapi.testclient import TestClient

        client = TestClient(create_app(self.workspace, actor="operator-a"))
        opened = client.post("/api/v1/runs/run-1/review-session", json={"gate_id":"gate3_material_selection"}).json()
        identity = opened["review_identity"]
        payload = {"session_id":opened["session_id"],"decision":"approve","scope_ids":["fragment01"],"strategy":{},"review_package_hash":identity["review_package_hash"],"state_revision":identity["state_revision"] + 1,"idempotency_key":"decision-stale"}
        response = client.post("/api/v1/runs/run-1/gates/gate3_material_selection/decisions", json=payload)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error_code"], "review_conflict")
        self.assertEqual(response.json()["current_revision"], 0)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI optional extra unavailable")
    def test_material_evidence_api_resumes_non_gate_pause(self) -> None:
        from fastapi.testclient import TestClient

        profiles = [{
            "asset_id": "asset-a", "source_path": "images/a.jpg", "sha256": "a" * 64,
            "media_type": "image", "width": 1080, "height": 1920, "duration_seconds": None,
        }]
        baseline = {"artifact_type": "content_baseline", "fragments": [{
            "fragment_id": "fragment01", "requirements": {
                "product_type": "透明桌垫", "required_semantics": ["claim-a"],
                "required_actions": ["show_product"], "allowed_media_types": ["image"],
                "forbidden_semantics": [], "expected_visual_seconds": 1.0,
            },
        }]}
        atomic_write_json(self.task / "asset_profiles.json", {"artifact_type": "asset_profiles", "asset_profiles": profiles})
        frozen = read_json_object(self.task / "g_b_frozen_input_snapshot.json")
        atomic_write_json(self.task / "g_b_frozen_input_snapshot.json", {
            **frozen,
            "asset_profiles_sha256": hashlib.sha256((self.task / "asset_profiles.json").read_bytes()).hexdigest(),
        })
        atomic_write_json(self.task / "content_baseline.json", baseline)
        atomic_write_json(self.task / "material_evidence_requirements.json", build_material_evidence_requirements(baseline, profiles, None))
        requirements_hash = hashlib.sha256((self.task / "material_evidence_requirements.json").read_bytes()).hexdigest()
        profiles_hash = hashlib.sha256((self.task / "asset_profiles.json").read_bytes()).hexdigest()
        self.store.update_state(lambda state: state | {
            "active_stage": "collect-material-evidence",
            "gate_status": {**state["gate_status"], "gate3_material_selection": "not_ready", "gate3": "not_ready"},
            "blockers": [{"category": "manual_classification_required", "requires_user": True}],
            "stage_status": {**state["stage_status"], "build-material-evidence-requirements": "not_started", "build-coverage-authoritative": "succeeded"},
        })
        calls: list[bool] = []

        class FakeRunner:
            def run(inner_self, *, resume: bool = False):
                calls.append(resume)
                return type("Result", (), {"status": "awaiting_user"})()

        RunRegistry(self.workspace).repair(
            "run-1", self.task,
            expected_registry_revision=RunRegistry(self.workspace)._read()["registry_revision"],
            actor="operator-a",
        )
        client = TestClient(
            create_app(self.workspace, actor="operator-a", runner_factory=lambda _: FakeRunner()),
            base_url="http://127.0.0.1:8765", client=("127.0.0.1", 50000),
        )
        page = client.get("/workbench/projects/new")
        nonce = re.search(r'<meta name="local-session-nonce" content="([^"]+)">', page.text).group(1)
        workspace = client.get("/api/v1/runs/run-1/workspace")
        self.assertEqual(workspace.status_code, 200, workspace.text)
        self.assertEqual(workspace.json()["process"]["current_stage"], "素材证据补充")
        response = client.post(
            "/api/v1/runs/run-1/material-evidence",
            headers={"Origin": "http://127.0.0.1:8765", "X-Local-Nonce": nonce},
            json={
                "expected_requirements_sha256": requirements_hash,
                "expected_asset_profiles_sha256": profiles_hash,
                "request_id": "api-evidence-1", "idempotency_key": "api-evidence-key-1",
                "annotations": [{
                    "asset_id": "asset-a", "source_path": "images/a.jpg", "sha256": "a" * 64,
                    "evidence_source": "manual_operator", "product_type": "透明桌垫",
                    "semantic_tags": ["claim-a"], "action_tags": ["show_product"],
                    "overlay_decision": "none", "evidence_window": {"kind": "frame", "frame_path": "images/a.jpg"},
                    "scores": {"semantic": 1, "action": 1, "composition": 0.8, "color": 0.8, "lighting": 0.8, "technical": 1},
                    "score_basis": "人工确认",
                }],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["resume_status"], "awaiting_user")
        self.assertEqual(calls, [True])


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI optional extra unavailable")
class ProjectInitializationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.workspace = Path(self._temporary.name).resolve()
        self.reference = self.workspace / "reference.mp4"
        self.reference.write_bytes(b"video")
        self.assets = self.workspace / "assets"
        self.assets.mkdir()
        self.client = TestClient(
            create_app(self.workspace, actor="operator-a"),
            base_url="http://127.0.0.1:8765",
            client=("127.0.0.1", 50000),
        )

    @staticmethod
    def _nonce(page: str) -> str:
        match = re.search(r'<meta name="local-session-nonce" content="([^"]+)">', page)
        if match is None:
            raise AssertionError("local session nonce is missing")
        return match.group(1)

    def test_project_pages_issue_session_and_protected_path_validation_rotates_nonce(self) -> None:
        page = self.client.get("/workbench/projects/new")
        self.assertEqual(page.status_code, 200)
        self.assertIn("local_session_id", page.cookies)
        nonce = self._nonce(page.text)

        response = self.client.post(
            "/api/v1/projects/path-validation",
            headers={"Origin": "http://127.0.0.1:8765", "X-Local-Nonce": nonce},
            json={"mode": "reference_video", "path": str(self.reference)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "valid")
        self.assertNotEqual(response.json()["next_nonce"], nonce)
        replay = self.client.post(
            "/api/v1/projects/path-validation",
            headers={"Origin": "http://127.0.0.1:8765", "X-Local-Nonce": nonce},
            json={"mode": "reference_video", "path": str(self.reference)},
        )
        self.assertEqual(replay.status_code, 403)

    def test_project_write_rejects_remote_peer_and_forged_origin(self) -> None:
        from fastapi.testclient import TestClient

        page = self.client.get("/workbench/projects/new")
        nonce = self._nonce(page.text)
        forged = self.client.post(
            "/api/v1/projects/path-validation",
            headers={"Origin": "https://evil.example", "X-Local-Nonce": nonce},
            json={"mode": "asset_directory", "path": str(self.assets)},
        )
        self.assertEqual(forged.status_code, 403)

        remote = TestClient(
            create_app(self.workspace, actor="operator-a"),
            base_url="http://127.0.0.1:8765",
            client=("192.0.2.10", 50000),
        )
        remote_page = remote.get("/workbench/projects/new")
        remote_nonce = self._nonce(remote_page.text)
        denied = remote.post(
            "/api/v1/projects/path-validation",
            headers={"Origin": "http://127.0.0.1:8765", "X-Local-Nonce": remote_nonce},
            json={"mode": "asset_directory", "path": str(self.assets)},
        )
        self.assertEqual(denied.status_code, 403)

    def test_draft_api_persists_normalized_brief(self) -> None:
        page = self.client.get("/workbench/projects/new")
        nonce = self._nonce(page.text)
        payload = {
            "reference_path": str(self.reference),
            "asset_root": str(self.assets),
            "product_name": "透明桌垫",
            "task_name": "tablemat-new",
            "platform": "抖音",
            "audience": "精致白领",
            "approved_claims": ["防水防油", "防水防油"],
            "forbidden_claims": ["无"],
            "output": {"aspect_ratio": "9:16", "width": 1080, "height": 1920, "fps": 60},
            "voice": {"provider": "doubao", "speaker": "zh_female_gaolengyujie_uranus_bigtts", "speed": 1.0},
            "request_id": "request-1",
            "idempotency_key": "draft-1",
        }
        saved = self.client.post(
            "/api/v1/projects/drafts",
            headers={"Origin": "http://127.0.0.1:8765", "X-Local-Nonce": nonce},
            json=payload,
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["draft"]["approved_claims"], ["防水防油"])
        self.assertEqual(saved.json()["draft"]["forbidden_claims"], [])
        self.assertTrue(saved.json()["project_url"].endswith("/stage0"))
        self.assertEqual(self.client.get("/api/v1/projects").json()[0]["task_name"], "tablemat-new")

    def test_picker_route_accepts_only_server_returned_fixed_mode_result(self) -> None:
        page = self.client.get("/workbench/projects/new")
        nonce = self._nonce(page.text)
        with patch(
            "remix_reference_video.api.pick_local_input_path",
            return_value={"status": "selected", "mode": "reference_video", "path": str(self.reference)},
        ) as picker:
            response = self.client.post(
                "/api/v1/projects/path-picker",
                headers={"Origin": "http://127.0.0.1:8765", "X-Local-Nonce": nonce},
                json={"mode": "reference_video", "script": "do shell script"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["path"], str(self.reference))
        picker.assert_called_once_with("reference_video")

    def test_stage0_freeze_and_runtime_unavailable_remain_separate(self) -> None:
        (self.assets / "product.jpg").write_bytes(b"image")
        nonce = self._nonce(self.client.get("/workbench/projects/new").text)
        draft_payload = {
            "reference_path": str(self.reference), "asset_root": str(self.assets),
            "product_name": "透明桌垫", "task_name": "tablemat-stage0", "platform": "抖音",
            "audience": "精致白领", "approved_claims": ["极简透明"], "forbidden_claims": [],
            "output": {"aspect_ratio": "9:16", "width": 1080, "height": 1920, "fps": 60},
            "voice": {"provider": "doubao", "speaker": "zh_female_gaolengyujie_uranus_bigtts", "speed": 1.0},
            "request_id": "draft-stage0", "idempotency_key": "draft-stage0",
        }
        saved = self.client.post(
            "/api/v1/projects/drafts",
            headers={"Origin": "http://127.0.0.1:8765", "X-Local-Nonce": nonce}, json=draft_payload,
        ).json()
        project_id = saved["draft"]["project_id"]
        nonce = saved["next_nonce"]
        with patch("remix_reference_video.asset_index.FFprobeAdapter", return_value=lambda _path, media_type: {"media_type": media_type, "width": 1080, "height": 1920}):
            stage0_response = self.client.post(
                f"/api/v1/projects/{project_id}/stage0",
                headers={"Origin": "http://127.0.0.1:8765", "X-Local-Nonce": nonce},
                json={"request_id": "stage0-api", "idempotency_key": "stage0-api"},
            )
        self.assertEqual(stage0_response.status_code, 200)
        stage0 = stage0_response.json()
        self.assertEqual(stage0["stage0_report"]["status"], "ready")
        nonce = stage0["next_nonce"]
        frozen_response = self.client.post(
            f"/api/v1/projects/{project_id}/freeze",
            headers={"Origin": "http://127.0.0.1:8765", "X-Local-Nonce": nonce},
            json={
                "draft_revision": 1, "report_sha256": stage0["stage0_report"]["report_sha256"],
                "date": "2026-08-20", "request_id": "freeze-api", "idempotency_key": "freeze-api",
            },
        )
        self.assertEqual(frozen_response.status_code, 200)
        frozen = Path(frozen_response.json()["project"]["frozen_root"])
        self.assertFalse((frozen / "pipeline_state.json").exists())
        nonce = frozen_response.json()["next_nonce"]
        unavailable = self.client.post(
            f"/api/v1/projects/{project_id}/start-cold",
            headers={"Origin": "http://127.0.0.1:8765", "X-Local-Nonce": nonce},
            json={"request_id": "cold-api", "idempotency_key": "cold-api"},
        )
        self.assertEqual(unavailable.status_code, 200)
        self.assertEqual(unavailable.json()["project"]["status"], "runtime_unavailable")
        self.assertFalse((frozen.parent / "cold").exists())


if __name__ == "__main__":
    unittest.main()
