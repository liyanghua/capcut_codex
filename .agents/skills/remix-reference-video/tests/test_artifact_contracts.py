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

_NARRATIVE = {
    "artifact_type": "narrative_coherence_report",
    "schema_id": "urn:capcut:remix-reference-video:artifact:narrative-coherence-report",
    "schema_version": "1.0.0",
    "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
    "implementation_version": "narrative-coherence-v1",
    "lifecycle_status": "ready",
    "input_hashes": {"content_baseline.json": "a" * 64},
    "status": "passed",
    "narrative_contract_version": "narrative_contract_v1",
    "continuity_lexicon_version": "continuity_lexicon_v1",
    "fragments": [
        {
            "fragment_id": "fragment01",
            "narrative_role": "开场情境",
            "required_actions": ["show_context"],
            "continuity_before": None,
            "continuity_after": "情境 → 问题",
            "approved_claim_ids": [],
            "evidence_row_ref": "fragment01",
            "coherence_status": "passed",
            "blocked_reasons": [],
            "business_explanation": "",
        }
    ],
    "checks": {"opening_context": "passed", "transition_coverage": "passed", "claim_density": "passed", "closing": "passed"},
    "blocked_fragment_ids": [],
    "allowed_resolutions": [],
}

_VISUAL = {
    "artifact_type": "visual_layout_report",
    "schema_id": "urn:capcut:remix-reference-video:artifact:visual-layout-report",
    "schema_version": "1.0.0",
    "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
    "implementation_version": "visual-layout-v1",
    "lifecycle_status": "ready",
    "input_hashes": {"material_manifest.json": "a" * 64},
    "status": "passed",
    "layout_policy_version": "visual_layout_policy_v1",
    "canvas": {"width": 1080, "height": 1920},
    "fragments": [
        {
            "fragment_id": "fragment01",
            "source_width": 1440,
            "source_height": 2560,
            "content_rect": {"x": 0, "y": 420, "w": 1080, "h": 1920},
            "scale_factor": 1.0,
            "crop_pixels": 0,
            "overlay_policy": "contain",
            "readability_status": "passed",
            "suggestion": "",
        }
    ],
    "blocked_fragment_ids": [],
    "allowed_resolutions": [],
}


class QualityReportContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def _write(self, name: str, value: object) -> None:
        atomic_write_json(self.root / name, value)

    def test_registry_declares_both_reports_as_track_b_derived(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        enum = registry["properties"]["artifact_type"]["enum"]
        self.assertIn("narrative_coherence_report", enum)
        self.assertIn("visual_layout_report", enum)
        index = {row["artifact_type"]: row for row in registry["x-artifacts"]}
        expected = {
            "narrative_coherence_report": "urn:capcut:remix-reference-video:artifact:narrative-coherence-report",
            "visual_layout_report": "urn:capcut:remix-reference-video:artifact:visual-layout-report",
        }
        for name, schema_id in expected.items():
            row = index[name]
            self.assertEqual(row["schema_id"], schema_id)
            self.assertEqual(row["track"], "B")
            self.assertEqual(row.get("activation"), "after_g_a")
            self.assertIs(row.get("production_state_authority"), False)
            self.assertTrue((SKILL_ROOT / row["schema_path"]).is_file(), row["schema_path"])
        discriminators = json.dumps(registry["oneOf"])
        self.assertIn("narrative-coherence-report", discriminators)
        self.assertIn("visual-layout-report", discriminators)

    def test_valid_reports_pass_schema_and_validator(self) -> None:
        cases = (
            ("narrative_coherence_report.json", "narrative-coherence-report.schema.json", _NARRATIVE),
            ("visual_layout_report.json", "visual-layout-report.schema.json", _VISUAL),
        )
        for filename, schema_name, value in cases:
            with self.subTest(schema_name):
                SnapshotSchemaValidator().assert_valid(value, schema_name)
                self._write(filename, value)
                result = ArtifactValidator(self.root).validate_quality_report(Path(filename))
                self.assertTrue(result.valid, result.errors)

    def test_quality_reports_reject_awaiting_user_lifecycle(self) -> None:
        value = dict(_NARRATIVE, lifecycle_status="awaiting_user")
        self._write("narrative_coherence_report.json", value)
        result = ArtifactValidator(self.root).validate_quality_report(Path("narrative_coherence_report.json"))
        self.assertFalse(result.valid)
        self.assertTrue(any("lifecycle_status" in error for error in result.errors), result.errors)

    def test_quality_reports_reject_missing_or_invalid_input_hashes(self) -> None:
        for bad in ({}, {"content_baseline.json": "not-a-sha256"}):
            with self.subTest(bad):
                value = dict(_NARRATIVE, input_hashes=bad)
                self._write("narrative_coherence_report.json", value)
                result = ArtifactValidator(self.root).validate_quality_report(Path("narrative_coherence_report.json"))
                self.assertFalse(result.valid)
                self.assertTrue(any("input_hashes" in error or "input hash" in error for error in result.errors), result.errors)
        value = {key: item for key, item in _NARRATIVE.items() if key != "input_hashes"}
        self._write("narrative_coherence_report.json", value)
        result = ArtifactValidator(self.root).validate_quality_report(Path("narrative_coherence_report.json"))
        self.assertFalse(result.valid)

    def test_quality_reports_reject_approval_fields_recursively(self) -> None:
        nested = json.loads(json.dumps(_NARRATIVE))
        nested["fragments"][0]["approval"] = {"decision": "approved"}
        self._write("narrative_coherence_report.json", nested)
        result = ArtifactValidator(self.root).validate_quality_report(Path("narrative_coherence_report.json"))
        self.assertFalse(result.valid)
        self.assertTrue(any("approval" in error for error in result.errors), result.errors)

        top = dict(_NARRATIVE, gate_status="approved")
        self._write("narrative_coherence_report.json", top)
        result = ArtifactValidator(self.root).validate_quality_report(Path("narrative_coherence_report.json"))
        self.assertFalse(result.valid)

    def test_quality_report_schema_rejects_approval_and_unknown_fields(self) -> None:
        with self.assertRaises(SnapshotSchemaError):
            SnapshotSchemaValidator().assert_valid(dict(_NARRATIVE, decision="approved"), "narrative-coherence-report.schema.json")
        with self.assertRaises(SnapshotSchemaError):
            SnapshotSchemaValidator().assert_valid(dict(_NARRATIVE, unknown_field="x"), "narrative-coherence-report.schema.json")
        with self.assertRaises(SnapshotSchemaError):
            SnapshotSchemaValidator().assert_valid(dict(_VISUAL, fragments=[dict(_VISUAL["fragments"][0], unknown_nested="x")]), "visual-layout-report.schema.json")

    def test_quality_report_schema_rejects_bad_statuses(self) -> None:
        with self.assertRaises(SnapshotSchemaError):
            SnapshotSchemaValidator().assert_valid(dict(_NARRATIVE, status="approved"), "narrative-coherence-report.schema.json")
        with self.assertRaises(SnapshotSchemaError):
            SnapshotSchemaValidator().assert_valid(dict(_VISUAL, status="awaiting_user"), "visual-layout-report.schema.json")


if __name__ == "__main__":
    unittest.main()
