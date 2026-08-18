from __future__ import annotations

import tempfile
import unittest
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from remix_reference_video.review_session import ReviewSessionError, ReviewSessionService
from remix_reference_video.storage import TaskStorage, atomic_write_json


class ReviewSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(); self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve(); (self.root / "gate_review_packages").mkdir()
        self.store = TaskStorage(self.root)
        self.store.initialize_state({"execution_mode":"track-b-production","run_id":"run-1","state_revision":0,"active_stage":"gate1","active_command":None,"stage_status":{},"gate_status":{"gate1":"awaiting_user"},"decisions":[],"artifacts":{},"blockers":[],"cache_summary":{}})
        atomic_write_json(self.root / "gate_review_packages/gate1.json", {"gate_id":"gate1","run_id":"run-1","state_revision":0,"input_hashes":{}})
        self.service = ReviewSessionService(self.root, actor="operator-a", role="operator")

    def test_open_binds_opaque_session_to_current_identity(self) -> None:
        session = self.service.open("gate1")
        self.assertTrue(session["session_id"])
        self.assertNotIn("task_dir", session)
        self.assertEqual(session["actor"], "operator-a")
        self.assertEqual(session["review_identity"]["review_package_hash"], self.service.package_hash("gate1"))

    def test_event_intents_use_service_time_and_reject_client_durations(self) -> None:
        session = self.service.open("gate1")
        event = self.service.record_intent(session["session_id"], "review.evidence_interaction", {"evidence_id":"recipe"})
        self.assertEqual(event["run_id"], "run-1")
        self.assertIn("occurred_at", event)
        with self.assertRaisesRegex(ReviewSessionError, "duration"):
            self.service.record_intent(session["session_id"], "review.active_stop", {"seconds": 12})

    def test_cross_gate_or_expired_session_is_rejected(self) -> None:
        session = self.service.open("gate1")
        with self.assertRaisesRegex(ReviewSessionError, "session"):
            self.service.record_intent("other", "review.heartbeat", {})
        self.store.append_event({"event_type":"review.pause","session_id":session["session_id"],"run_id":"run-1","gate_id":"gate1"}, state_revision=0)
        with self.assertRaisesRegex(ReviewSessionError, "paused"):
            self.service.record_intent(session["session_id"], "review.heartbeat", {})

    def test_browser_cannot_emit_server_owned_events(self) -> None:
        session = self.service.open("gate1")
        for event_type in ("review.decision_accepted", "review.decision_conflicted", "review.rework_completed"):
            with self.assertRaisesRegex(ReviewSessionError, "server-owned"):
                self.service.record_intent(session["session_id"], event_type, {})

    def test_expired_session_cannot_be_revived_with_active_start(self) -> None:
        session = self.service.open("gate1")
        events_path = self.root / "pipeline_events.jsonl"
        lines = events_path.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines]
        records[-1]["occurred_at"] = (datetime.now(UTC) - timedelta(seconds=61)).isoformat().replace("+00:00", "Z")
        events_path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ReviewSessionError, "heartbeat expired"):
            self.service.record_intent(session["session_id"], "review.active_start", {"active_interval_id": "a"})


if __name__ == "__main__": unittest.main()
