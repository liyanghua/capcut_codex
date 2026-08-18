from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.review_session import ReviewSessionService
from remix_reference_video.storage import TaskStorage, atomic_write_json, read_json_object, read_jsonl_records
from remix_reference_video.workbench_decision import WorkbenchConflict, WorkbenchDecisionService


class WorkbenchDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(); self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve(); (self.root / "gate_review_packages").mkdir()
        self.store = TaskStorage(self.root)
        self.store.initialize_state({"execution_mode":"track-b-production","run_id":"run-1","state_revision":0,"active_stage":"gate1","active_command":None,"stage_status":{},"gate_status":{"gate1":"awaiting_user"},"decisions":[],"artifacts":{},"blockers":[],"cache_summary":{}})
        evidence = self.root / "recipe.json"; evidence.write_text("{}\n", encoding="utf-8")
        digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
        atomic_write_json(self.root / "gate_review_packages/gate1.json", {"gate_id":"gate1","run_id":"run-1","state_revision":0,"created_at":"2026-08-17T10:00:00Z","input_hashes":{"recipe.json":digest}})
        self.sessions = ReviewSessionService(self.root, actor="operator-a")
        self.session = self.sessions.open("gate1")
        self.service = WorkbenchDecisionService(self.root, actor="operator-a")

    def _body(self, **overrides):
        value = {"decision":"approve","scope_ids":["recipe.json"],"strategy":{},"note":"通过","review_package_hash":self.sessions.package_hash("gate1"),"state_revision":0,"idempotency_key":"decision-1"}
        value.update(overrides); return value

    def test_approve_uses_server_actor_and_gate_scope(self) -> None:
        result = self.service.submit(session_id=self.session["session_id"], gate_id="gate1", payload=self._body(actor="spoofed"))
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(result["actor"], "operator-a")
        self.assertEqual(result["scope_type"], "artifact_set")
        events = [event["event_type"] for event in read_jsonl_records(self.root / "pipeline_events.jsonl")]
        self.assertLess(events.index("review.decision_submitted"), events.index("review.decision_accepted"))

    def test_idempotency_replay_and_payload_conflict(self) -> None:
        first = self.service.submit(session_id=self.session["session_id"], gate_id="gate1", payload=self._body())
        second = self.service.submit(session_id=self.session["session_id"], gate_id="gate1", payload=self._body())
        self.assertEqual(first, second)
        with self.assertRaisesRegex(WorkbenchConflict, "idempotency"):
            self.service.submit(session_id=self.session["session_id"], gate_id="gate1", payload=self._body(note="different"))

    def test_stale_revision_returns_current_conflict(self) -> None:
        with self.assertRaises(WorkbenchConflict) as caught:
            self.service.submit(session_id=self.session["session_id"], gate_id="gate1", payload=self._body(state_revision=9))
        self.assertEqual(caught.exception.current_revision, 0)
        self.assertTrue(caught.exception.refresh_path.endswith("/review"))

    def test_rejection_requires_business_reason(self) -> None:
        with self.assertRaisesRegex(WorkbenchConflict, "rejection reason"):
            self.service.submit(session_id=self.session["session_id"], gate_id="gate1", payload=self._body(decision="reject", note=""))

    def test_approval_is_blocked_by_current_workspace_risk(self) -> None:
        self.store.update_state(lambda state: {**state, "blockers": [{"requires_user": True, "detail": "缺少关键素材"}]})
        package_path = self.root / "gate_review_packages/gate1.json"
        package = read_json_object(package_path)
        package["state_revision"] = self.store.read_state()["state_revision"]
        atomic_write_json(package_path, package)
        session = ReviewSessionService(self.root, actor="operator-a").open("gate1")
        identity = session["review_identity"]
        payload = self._body(review_package_hash=identity["review_package_hash"], state_revision=identity["state_revision"], idempotency_key="blocked-approval")
        with self.assertRaisesRegex(WorkbenchConflict, "阻塞"):
            self.service.submit(session_id=session["session_id"], gate_id="gate1", payload=payload)


if __name__ == "__main__": unittest.main()
