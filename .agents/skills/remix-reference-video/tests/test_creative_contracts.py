from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.artifact_validator import ArtifactValidator
from remix_reference_video.snapshot_schema_validator import SnapshotSchemaError, SnapshotSchemaValidator
from remix_reference_video.storage import atomic_write_json


SKILL_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = SKILL_ROOT / "schemas" / "v2-alpha.registry.schema.json"

_ENVELOPE = {
    "schema_version": "1.0.0",
    "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
}


def _artifact(artifact_type: str) -> dict[str, object]:
    value: dict[str, object] = {
        "artifact_type": artifact_type,
        "schema_id": f"urn:capcut:remix-reference-video:artifact:{artifact_type.replace('_', '-')}",
        **_ENVELOPE,
        "implementation_version": "creative-contract-v1",
        "lifecycle_status": "ready",
        "input_hashes": {"gate_input.json": "a" * 64},
    }
    if artifact_type == "decomposition_bundle":
        value["candidates"] = [{"decomposition_id": "decomp-1", "strategy_id": "hybrid_commerce_v1"}]
    elif artifact_type == "creative_objective":
        value["objective_contract_version"] = "creative_objective_v1"
        value["objectives"] = [{"objective_id": "hook", "weight": 1.0, "required": True}]
    elif artifact_type == "remix_strategy_candidates":
        value["candidates"] = [{"strategy_id": "balanced_remix_v1", "status": "passed"}]
    elif artifact_type == "script_candidates":
        value["candidates"] = [{"script_candidate_id": "script-1", "status": "candidate"}]
    elif artifact_type == "script_candidate_validation_report":
        value["candidates"] = [{"script_candidate_id": "script-1", "status": "passed"}]
    elif artifact_type == "shot_quality_report":
        value["status"] = "passed"
        value["shots"] = []
    elif artifact_type == "enhancement_plan":
        value["status"] = "ready"
        value["shot_id"] = "shot-1"
    elif artifact_type == "final_content_diagnostic_report":
        value["status"] = "passed"
        value["checks"] = []
    return value


CREATIVE_TYPES = (
    "decomposition_bundle",
    "creative_objective",
    "remix_strategy_candidates",
    "script_candidates",
    "script_candidate_validation_report",
    "shot_quality_report",
    "enhancement_plan",
    "final_content_diagnostic_report",
)


class CreativeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_registry_registers_all_creative_artifacts(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        enum = registry["properties"]["artifact_type"]["enum"]
        index = {row["artifact_type"]: row for row in registry["x-artifacts"]}
        discriminators = json.dumps(registry["oneOf"])
        for artifact_type in CREATIVE_TYPES:
            self.assertIn(artifact_type, enum)
            self.assertIn(artifact_type, index)
            row = index[artifact_type]
            self.assertEqual(row["track"], "B")
            self.assertEqual(row["activation"], "after_g_a")
            self.assertIs(row.get("production_state_authority"), False)
            self.assertTrue((SKILL_ROOT / row["schema_path"]).is_file(), row["schema_path"])
            self.assertIn(artifact_type.replace("_", "-"), discriminators)

    def test_all_creative_artifacts_validate_with_strict_schema(self) -> None:
        validator = SnapshotSchemaValidator()
        for artifact_type in CREATIVE_TYPES:
            with self.subTest(artifact_type):
                validator.assert_valid(_artifact(artifact_type), f"{artifact_type.replace('_', '-')}.schema.json")

    def test_machine_artifacts_reject_approval_fields_and_non_ready_lifecycle(self) -> None:
        validator = ArtifactValidator(self.root)
        for artifact_type in CREATIVE_TYPES:
            with self.subTest(artifact_type):
                value = _artifact(artifact_type)
                value["lifecycle_status"] = "awaiting_user"
                value["approval"] = {"status": "approved"}
                path = self.root / f"{artifact_type}.json"
                atomic_write_json(path, value)
                result = validator.validate_quality_report(path)
                self.assertFalse(result.valid)
                self.assertTrue(any("approval" in error for error in result.errors), result.errors)
                self.assertTrue(any("lifecycle" in error for error in result.errors), result.errors)

    def test_machine_artifacts_reject_reserved_decision_keys_recursively(self) -> None:
        validator = ArtifactValidator(self.root)
        for reserved in ("gate_status", "decision", "approval_status"):
            with self.subTest(reserved):
                value = _artifact("shot_quality_report")
                value["shots"] = [{"shot_id": "shot-1", reserved: "approved"}]
                path = self.root / f"reserved-{reserved}.json"
                atomic_write_json(path, value)
                result = validator.validate_quality_report(path)
                self.assertFalse(result.valid)
                self.assertTrue(any(reserved in error for error in result.errors), result.errors)

    def test_schema_rejects_unknown_fields_and_bad_hashes(self) -> None:
        value = _artifact("creative_objective")
        with self.assertRaises(SnapshotSchemaError):
            SnapshotSchemaValidator().assert_valid({**value, "unknown": True}, "creative-objective.schema.json")
        with self.assertRaises(SnapshotSchemaError):
            SnapshotSchemaValidator().assert_valid({**value, "input_hashes": {"brief": "not-sha256"}}, "creative-objective.schema.json")


if __name__ == "__main__":
    unittest.main()
