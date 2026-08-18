from __future__ import annotations

import unittest

from remix_reference_video.process_assessment import ProcessAssessmentBuilder


class ProcessAssessmentTrustedTimingTests(unittest.TestCase):
    def test_server_event_times_measure_wait_touch_decision_and_rework(self) -> None:
        events = [
            {"event_type":"command.awaiting_user","gate_id":"gate1","occurred_at":"2026-08-17T10:00:00Z"},
            {"event_type":"review.opened","gate_id":"gate1","session_id":"s1","occurred_at":"2026-08-17T10:01:00Z"},
            {"event_type":"review.evidence_interaction","gate_id":"gate1","session_id":"s1","occurred_at":"2026-08-17T10:01:10Z","payload":{"seconds":999}},
            {"event_type":"review.active_start","gate_id":"gate1","session_id":"s1","occurred_at":"2026-08-17T10:01:20Z","payload":{"at_seconds":0}},
            {"event_type":"review.heartbeat","gate_id":"gate1","session_id":"s1","occurred_at":"2026-08-17T10:01:40Z"},
            {"event_type":"review.active_stop","gate_id":"gate1","session_id":"s1","occurred_at":"2026-08-17T10:02:00Z","payload":{"at_seconds":1}},
            {"event_type":"review.decision_submitted","gate_id":"gate1","session_id":"s1","occurred_at":"2026-08-17T10:03:00Z"},
            {"event_type":"review.decision_accepted","gate_id":"gate1","session_id":"s1","occurred_at":"2026-08-17T10:03:01Z"},
            {"event_type":"change.applied","gate_id":"gate1","session_id":"s1","occurred_at":"2026-08-17T10:05:00Z"},
            {"event_type":"review.rework_completed","gate_id":"gate1","session_id":"s1","occurred_at":"2026-08-17T10:07:00Z"},
        ]
        state = {"run_id":"run-1","decisions":[],"gate_status":{}}
        result = ProcessAssessmentBuilder().build(state=state, events=events, metrics=[], run_id="run-1", execution_mode="track-b-production")
        metrics = result["metrics"]
        self.assertEqual(metrics["human_wait_seconds"]["value"], 70.0)
        self.assertEqual(metrics["operator_touch_seconds"]["value"], 40.0)
        self.assertEqual(metrics["decision_seconds"]["value"], 111.0)
        self.assertEqual(metrics["rework_seconds"]["value"], 120.0)
        self.assertEqual(result["gate_return_count"], 1)

    def test_missing_boundaries_are_not_measured_and_client_times_are_ignored(self) -> None:
        result = ProcessAssessmentBuilder().build(
            state={"run_id":"run-1","decisions":[],"gate_status":{}},
            events=[{"event_type":"review.evidence_interaction","occurred_at":"2026-08-17T10:00:00Z","payload":{"seconds":1234}}],
            metrics=[], run_id="run-1", execution_mode="track-b-production",
        )
        self.assertEqual(result["metrics"]["human_wait_seconds"]["measurement_status"], "not_measured")
        self.assertEqual(result["metrics"]["operator_touch_seconds"]["measurement_status"], "not_measured")
        self.assertEqual(result["metrics"]["decision_seconds"]["measurement_status"], "not_measured")


if __name__ == "__main__": unittest.main()
