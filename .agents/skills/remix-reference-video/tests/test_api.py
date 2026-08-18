from __future__ import annotations

import importlib.util
import hashlib
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.api import ProgressProjector, create_app
from remix_reference_video.run_registry import RunRegistry
from remix_reference_video.storage import TaskStorage, atomic_write_json
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
        self.assertIn("data-action=\"approve\"", page.text)
        self.assertIn("data-action=\"reject\"", page.text)
        self.assertIn("data-action=\"request_changes\"", page.text)
        self.assertIn("id=\"change-fields\"", page.text)
        self.assertNotIn("id=\"change-payload\"", page.text)
        script = client.get("/static/review_workbench.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("new EventSource", script.text)
        self.assertNotIn('addEventListener("revision", () => location.reload())', script.text)
        self.assertIn("Number(payload.state_revision) > Number(state.view.state_revision)", script.text)
        self.assertIn("<video", script.text)
        self.assertIn("<audio", script.text)
        self.assertIn("<img", script.text)
        self.assertEqual(client.get("/static/review_workbench.js").status_code, 200)

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


if __name__ == "__main__":
    unittest.main()
