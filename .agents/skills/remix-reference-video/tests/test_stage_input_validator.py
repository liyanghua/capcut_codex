from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.stage_input_validator import StageInputValidator


class StageInputValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "stage_inputs").mkdir()
        (self.root / "recipe.json").write_text("recipe", encoding="utf-8")
        self.digest = hashlib.sha256(b"recipe").hexdigest()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_input(self, **overrides: object) -> Path:
        value: dict[str, object] = {
            "artifact_type": "stage_input",
            "schema_id": "urn:capcut:remix-reference-video:artifact:stage-input",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "stage_id": "compile-blueprint",
            "producer": {"kind": "agent", "id": "operator", "version": "1"},
            "created_at": "2026-08-16T10:00:00Z",
            "lifecycle_status": "awaiting_user",
            "input_hashes": {"recipe.json": self.digest},
            "payload": {"target_fragments": []},
        }
        value.update(overrides)
        path = self.root / "stage_inputs" / "compile-blueprint.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_valid_handoff_and_declared_hashes_pass(self) -> None:
        result = StageInputValidator(self.root).validate(
            self.write_input(),
            expected_stage_id="compile-blueprint",
            expected_input_hashes={"recipe.json": self.digest},
        )
        self.assertTrue(result.valid, result.errors)

    def test_missing_envelope_stage_and_lifecycle_are_rejected(self) -> None:
        path = self.write_input(schema_version="0", stage_id="other", lifecycle_status="approved")
        result = StageInputValidator(self.root).validate(path, expected_stage_id="compile-blueprint")
        self.assertFalse(result.valid)
        self.assertTrue(any("schema_version" in error for error in result.errors))
        self.assertTrue(any("stage_id" in error for error in result.errors))
        self.assertTrue(any("lifecycle_status" in error for error in result.errors))

    def test_hash_mismatch_and_expected_inputs_are_rejected(self) -> None:
        path = self.write_input(input_hashes={"recipe.json": "0" * 64})
        result = StageInputValidator(self.root).validate(
            path, expected_input_hashes={"recipe.json": self.digest}
        )
        self.assertFalse(result.valid)
        self.assertTrue(any("hash mismatch" in error for error in result.errors))
        self.assertTrue(any("declared inputs" in error for error in result.errors))

    def test_escape_and_symlink_inputs_are_rejected(self) -> None:
        outside = self.root.parent / "outside-stage-input.txt"
        outside.write_text("outside", encoding="utf-8")
        try:
            path = self.write_input(input_hashes={"../outside-stage-input.txt": self.digest})
            result = StageInputValidator(self.root).validate(path)
            self.assertFalse(result.valid)
            self.assertTrue(any("task-relative" in error for error in result.errors))
            link = self.root / "linked-recipe.json"
            link.symlink_to(self.root / "recipe.json")
            path = self.write_input(input_hashes={"linked-recipe.json": self.digest})
            result = StageInputValidator(self.root).validate(path)
            self.assertFalse(result.valid)
            self.assertTrue(any("symlink" in error for error in result.errors))
        finally:
            outside.unlink(missing_ok=True)

    def test_gate_approval_fields_are_rejected_even_in_payload(self) -> None:
        result = StageInputValidator(self.root).validate(
            self.write_input(payload={"approval": {"decision": "approved"}})
        )
        self.assertFalse(result.valid)
        self.assertTrue(any("approval fields" in error for error in result.errors))

    def test_validate_all_uses_filename_stage_id_and_is_read_only(self) -> None:
        self.write_input()
        before = (self.root / "stage_inputs" / "compile-blueprint.json").read_bytes()
        result = StageInputValidator(self.root).validate_all()
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(before, (self.root / "stage_inputs" / "compile-blueprint.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
