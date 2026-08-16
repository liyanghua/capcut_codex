from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.api import ProgressProjector, create_app
from remix_reference_video.storage import TaskStorage


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
                "gate_status": {"gate1": "approved", "gate2": "approved", "gate3": "awaiting_user"},
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
        self.store.append_event({"event_type": "stage.started"}, state_revision=0)
        self.store.append_event({"event_type": "stage.progress"}, state_revision=0)
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
    def test_fastapi_routes_are_read_only(self) -> None:
        app = create_app(self.workspace)
        methods = {
            method
            for route in app.routes
            for method in getattr(route, "methods", set())
            if not str(getattr(route, "path", "")).startswith("/openapi")
        }
        self.assertFalse(methods.intersection({"POST", "PUT", "PATCH", "DELETE"}))


if __name__ == "__main__":
    unittest.main()
