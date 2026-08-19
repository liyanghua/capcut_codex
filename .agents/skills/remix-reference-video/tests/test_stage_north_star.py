from __future__ import annotations

import unittest

from remix_reference_video.stage_north_star import StageNorthStarBuilder


class StageNorthStarTests(unittest.TestCase):
    def test_first_pass_rates_use_first_bound_package_not_candidate_count(self) -> None:
        packages = [
            {"gate_id": "gate1", "package_revision": 1, "input_hash": "a" * 64, "status": "awaiting_user"},
            {"gate_id": "gate1", "package_revision": 2, "input_hash": "a" * 64, "status": "awaiting_user"},
            {"gate_id": "gate4_pre_generation", "package_revision": 4, "input_hash": "b" * 64, "status": "awaiting_user"},
        ]
        decisions = [
            {"gate_id": "gate1", "package_revision": 1, "decision": "changes_requested"},
            {"gate_id": "gate1", "package_revision": 2, "decision": "approved"},
            {"gate_id": "gate4_pre_generation", "package_revision": 4, "decision": "approved"},
        ]
        result = StageNorthStarBuilder().build(packages=packages, decisions=decisions)
        self.assertEqual(result["decomposition_first_pass"]["value"], 0.0)
        self.assertEqual(result["script_first_pass"]["value"], 1.0)
        self.assertEqual(result["decomposition_first_pass"]["sample_size"], 1)
        self.assertEqual(result["rework_rounds"]["value"], 1)

    def test_weighted_objective_and_required_actions_use_authoritative_sources(self) -> None:
        result = StageNorthStarBuilder().build(
            creative_objective={"objectives": [{"objective_id": "hook", "weight": 0.6, "required": True}, {"objective_id": "proof", "weight": 0.4, "required": True}]},
            objective_results={"hook": "passed", "proof": "blocked"},
            approved_shot_ids=["s1", "s2"],
            shot_quality_report={"shots": [{"shot_id": "s1", "action_results": [{"action_id": "show", "status": "passed", "evidence_ref": "proxy#t=0,1"}]}, {"shot_id": "s2", "action_results": [{"action_id": "wipe", "status": "passed"}]}]},
        )
        self.assertEqual(result["weighted_objective_coverage"]["value"], 0.6)
        self.assertEqual(result["shot_intent_completion"]["value"], 0.5)

    def test_missing_sources_are_not_measured_and_timing_reuses_interval_model(self) -> None:
        missing = StageNorthStarBuilder().build()
        self.assertTrue(all(row["measurement_status"] == "not_measured" for key, row in missing.items() if key != "rework_rounds"))
        events = [
            {"event_type": "review.evidence_interaction", "gate_id": "gate1", "session_id": "s1", "occurred_at": "2026-08-19T10:00:00Z"},
            {"event_type": "review.active_start", "gate_id": "gate1", "session_id": "s1", "occurred_at": "2026-08-19T10:00:10Z", "payload": {"active_interval_id": "a"}},
            {"event_type": "review.active_stop", "gate_id": "gate1", "session_id": "s1", "occurred_at": "2026-08-19T10:00:30Z", "payload": {"active_interval_id": "a"}},
            {"event_type": "review.decision_submitted", "gate_id": "gate1", "session_id": "s1", "occurred_at": "2026-08-19T10:00:35Z"},
            {"event_type": "review.decision_accepted", "gate_id": "gate1", "session_id": "s1", "occurred_at": "2026-08-19T10:00:36Z"},
        ]
        measured = StageNorthStarBuilder().build(events=events)
        self.assertEqual(measured["effective_decision_seconds"]["value"], 36.0)


if __name__ == "__main__":
    unittest.main()
