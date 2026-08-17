from __future__ import annotations

import unittest
import json
from pathlib import Path

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

    def test_registry_contains_review_artifacts_and_all_change_contracts(self) -> None:
        registry = json.loads(
            (Path(__file__).resolve().parents[1] / "schemas/v2-alpha.registry.schema.json").read_text(encoding="utf-8")
        )
        artifacts = {item["artifact_type"]: item for item in registry["x-artifacts"]}
        for artifact_type in ("gate_review_view", "gate_review_sheet"):
            item = artifacts[artifact_type]
            self.assertEqual(item["track"], "B")
            self.assertEqual(item["activation"], "after_g_a")
            self.assertTrue(item["schema_path"].endswith(".schema.json"))
        input_types = {item["artifact_type"] for item in registry["x-input-contracts"]}
        for change_type in ("copy", "claim_scope", "voice", "material", "range", "rerecord", "boundary", "structural"):
            self.assertIn(f"change_request_{change_type}", input_types)
        artifact_enum = registry["properties"]["artifact_type"]["enum"]
        self.assertFalse(any(item.startswith("change_request_") for item in artifact_enum))

    def test_gate_review_view_requires_business_decision_shape(self) -> None:
        value = {
            "artifact_type": "gate_review_view",
            "schema_id": "urn:capcut:remix-reference-video:artifact:gate-review-view",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "snapshot_id": "review-1",
            "run_id": "run-1",
            "gate_id": "gate3_material_selection",
            "state_revision": 7,
            "bound_package_sha256": "a" * 64,
            "lifecycle_status": "ready",
        }
        errors = SnapshotSchemaValidator().validate(value, "gate-review-view.schema.json")
        for field in ("review_meta", "business_summary", "available_actions", "evidence", "risks", "impact_context"):
            self.assertTrue(any(field in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
