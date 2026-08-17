from __future__ import annotations

import unittest

from remix_reference_video.snapshot_schema_validator import SnapshotSchemaValidator


class SnapshotSchemaValidatorTests(unittest.TestCase):
    def test_not_scored_snapshot_cannot_have_numeric_total(self) -> None:
        value = {
            "artifact_type": "phase6_score_snapshot",
            "schema_id": "urn:capcut:remix-reference-video:artifact:phase6-score-snapshot",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "snapshot_id": "s1", "run_id": "r1", "measurement_status": "not_scored",
            "framework_stages": [{"framework_stage_id": stage, "rubric_items": [], "stage_output_quality_score": None, "measurement_status": "not_scored"} for stage in ("performance_proven_video", "blueprint", "controlled_mutation", "retrieval", "reconstruction")],
            "video_quality_score": 90, "g_b_thresholds_met": False, "owner_g_b_approval_required": True,
        }
        errors = SnapshotSchemaValidator().validate(value, "phase6-score-snapshot.schema.json")
        self.assertTrue(any("video_quality_score" in error for error in errors))

    def test_input_contract_is_not_an_artifact_shape(self) -> None:
        self.assertEqual(SnapshotSchemaValidator().validate({"framework_stages": []}, "inputs/phase6-rubric-input.schema.json"), ("/framework_stages: [] is too short",))


if __name__ == "__main__":
    unittest.main()
