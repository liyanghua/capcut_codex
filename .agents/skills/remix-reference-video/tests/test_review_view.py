from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.review_view import ReviewViewBuilder
from remix_reference_video.storage import TaskStorage, atomic_write_json


GATES = (
    "gate1", "gate2", "gate3_material_selection", "gate3_evidence_closure",
    "gate4_pre_generation", "gate4_post_generation", "gate5",
)


class ReviewViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.store = TaskStorage(self.root)
        self.store.initialize_state({
            "execution_mode": "track-b-production", "run_id": "run-1", "state_revision": 0,
            "active_stage": "gate1", "active_command": None, "stage_status": {},
            "gate_status": {gate: "awaiting_user" if gate == "gate1" else "not_ready" for gate in GATES},
            "decisions": [], "artifacts": {}, "blockers": [], "cache_summary": {},
        })
        (self.root / "gate_review_packages").mkdir()
        self.builder = ReviewViewBuilder(self.root)

    def _package(self, gate: str) -> None:
        atomic_write_json(self.root / "gate_review_packages" / f"{gate}.json", {
            "gate_id": gate, "run_id": "run-1", "state_revision": 0,
            "created_at": "2026-08-17T10:00:00Z", "input_hashes": {"evidence.json": "a" * 64},
            "known_nonblocking_risks": ["源画面有可见文字"],
        })

    def test_all_seven_gates_have_business_decision_views(self) -> None:
        for gate in GATES:
            with self.subTest(gate=gate):
                self._package(gate)
                view = self.builder.build(gate)
                self.assertEqual(view["gate_id"], gate)
                self.assertEqual(view["run_id"], "run-1")
                self.assertEqual(view["available_actions"], ["approve", "reject", "request_changes"])
                self.assertTrue(view["review_meta"]["business_name"])
                self.assertTrue(view["review_meta"]["decision_question"])
                self.assertLessEqual(len(view["business_summary"]["business_impacts"]), 3)
                self.assertEqual(view["risks"][0]["blocking"], False)
                self.assertEqual(view["trusted_service_time"], "2026-08-17T10:00:00Z")
                self.assertEqual(view["policy_id"], "review-workbench-p0b")
                self.assertEqual(view["policy_version"], "1.0.0")
                self.assertIn("contract_version", view["source_versions"])
                self.assertTrue(view["idempotency_key"])

    def test_snapshot_is_deterministic_and_does_not_mutate_state(self) -> None:
        self._package("gate1")
        before = (self.root / "pipeline_state.json").read_bytes()
        first = self.builder.write_snapshot("gate1")
        first_bytes = {name: Path(path).read_bytes() for name, path in first.items()}
        second = self.builder.write_snapshot("gate1")
        self.assertEqual(first, second)
        self.assertEqual(first_bytes, {name: Path(path).read_bytes() for name, path in second.items()})
        self.assertEqual((self.root / "pipeline_state.json").read_bytes(), before)
        self.assertIn("只需确认", Path(first["markdown_path"]).read_text(encoding="utf-8"))
        self.assertIn("通过", Path(first["html_path"]).read_text(encoding="utf-8"))
        sheet = json.loads(Path(first["sheet_path"]).read_text(encoding="utf-8"))
        self.assertTrue(sheet["snapshot_id"])
        self.assertEqual(sheet["trusted_service_time"], "2026-08-17T10:00:00Z")
        self.assertEqual(sheet["source_versions"]["skill_version"], "2.0.0-alpha.1")

    def test_stale_state_and_last_approval_diff_are_explicit(self) -> None:
        self._package("gate2")
        self.store.update_state(lambda state: state | {
            "gate_status": {**state["gate_status"], "gate2": "stale"},
            "decisions": [{"gate_id": "gate2", "decision": "approved", "input_hashes": {"old.json": "b" * 64}}],
        })
        atomic_write_json(self.root / "gate_review_packages/gate2.json", {
            "gate_id": "gate2", "run_id": "run-1", "state_revision": 1,
            "created_at": "2026-08-17T10:01:00Z", "input_hashes": {"new.json": "c" * 64},
        })
        view = self.builder.build("gate2")
        self.assertEqual(view["lifecycle_status"], "stale")
        diff = view["impact_context"]["last_approval_diff"]
        self.assertEqual(diff["changed"], ["new.json", "old.json"])

    def test_change_options_expose_business_choices_without_manual_hash_entry(self) -> None:
        self._package("gate3_material_selection")
        atomic_write_json(self.root / "matches.json", {"fragments":[{"fragment_id":"fragment01","candidates":[{"asset_id":"asset-1","source_id":"桌垫近景.mp4","sha256":"d"*64,"broad_ranges":[{"start_seconds":0.0,"end_seconds":3.0}]}]}]})
        atomic_write_json(self.root / "fragment_plan.json", {"fragments":[{"fragment_id":"fragment01","approved_broad_range":{"start_seconds":0.2,"end_seconds":2.8}}]})

        view = self.builder.build("gate3_material_selection")

        options = view["impact_context"]["change_options"]
        self.assertEqual(options["fragments"][0]["fragment_id"], "fragment01")
        self.assertEqual(options["fragments"][0]["candidates"][0]["label"], "桌垫近景.mp4")
        self.assertEqual(options["fragments"][0]["candidates"][0]["candidate_id"], "asset-1")
        self.assertEqual(options["fragments"][0]["range"], {"start_seconds":0.2,"end_seconds":2.8})


if __name__ == "__main__":
    unittest.main()
