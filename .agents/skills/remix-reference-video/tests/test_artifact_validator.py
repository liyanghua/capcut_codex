from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.artifact_validator import ArtifactValidator
from remix_reference_video.cli import audit_task
from remix_reference_video.storage import atomic_write_json


class ArtifactValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.validator = ArtifactValidator(self.root)

    @staticmethod
    def envelope(artifact_type: str) -> dict[str, object]:
        return {
            "artifact_type": artifact_type,
            "schema_id": f"urn:test:{artifact_type}",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
        }

    @staticmethod
    def sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def test_validates_envelope_and_expected_type(self) -> None:
        path = self.root / "recipe.json"
        atomic_write_json(path, self.envelope("recipe"))

        self.assertTrue(self.validator.validate_artifact(path, "recipe").valid)
        invalid = self.validator.validate_artifact(path, "shot_blueprint")
        self.assertFalse(invalid.valid)
        self.assertTrue(any("artifact_type" in item for item in invalid.errors))

    def test_rejects_path_escape_symlink_and_hash_mismatch(self) -> None:
        outside = self.root.parent / "outside-artifact.json"
        outside.write_text("outside", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        link = self.root / "linked.json"
        link.symlink_to(outside)

        self.assertFalse(self.validator.validate_hash("../outside-artifact.json", "0" * 64).valid)
        self.assertFalse(self.validator.validate_hash("linked.json", self.sha256(outside)).valid)
        local = self.root / "local.json"
        local.write_text("local", encoding="utf-8")
        self.assertFalse(self.validator.validate_hash("local.json", "0" * 64).valid)

    def test_validates_timeline_is_within_gate3_broad_ranges(self) -> None:
        fragment_plan = self.envelope("fragment_plan") | {
            "fragments": [
                {
                    "fragment_id": "fragment01",
                    "approved_broad_range": {"start_seconds": 1.0, "end_seconds": 4.0},
                }
            ]
        }
        timeline = self.envelope("reconstruction_timeline") | {
            "fragments": [
                {
                    "fragment_id": "fragment01",
                    "source_start_seconds": 1.5,
                    "source_end_seconds": 3.5,
                }
            ]
        }

        self.assertTrue(self.validator.validate_timeline(timeline, fragment_plan).valid)
        timeline["fragments"][0]["source_end_seconds"] = 4.1  # type: ignore[index]
        self.assertFalse(self.validator.validate_timeline(timeline, fragment_plan).valid)

    def test_gate5_bundle_requires_registered_current_hashes(self) -> None:
        names = (
            "remix.mp4",
            "captions.srt",
            "final_validation_report.json",
            "render_report.json",
            "jianying_import_manifest.json",
        )
        artifacts: dict[str, object] = {}
        for name in names:
            path = self.root / name
            path.write_bytes(name.encode("utf-8"))
            artifacts[name] = {"path": name, "sha256": self.sha256(path)}

        self.assertTrue(self.validator.validate_gate5_bundle(artifacts).valid)
        (self.root / "remix.mp4").write_bytes(b"changed")
        self.assertFalse(self.validator.validate_gate5_bundle(artifacts).valid)

    def test_production_audit_validates_registered_artifact_hashes(self) -> None:
        artifact = self.root / "recipe.json"
        atomic_write_json(artifact, self.envelope("recipe"))
        atomic_write_json(
            self.root / "pipeline_state.json",
            {
                "execution_mode": "track-b-production",
                "run_id": "run-1",
                "state_revision": 0,
                "active_stage": None,
                "active_command": None,
                "stage_status": {},
                "gate_status": {},
                "decisions": [],
                "artifacts": {
                    "recipe": {"path": "recipe.json", "sha256": self.sha256(artifact)}
                },
                "blockers": [],
                "cache_summary": {},
            },
        )

        self.assertEqual(audit_task(self.root)["status"], "passed")
        artifact.write_text("changed", encoding="utf-8")
        failed = audit_task(self.root)
        self.assertEqual(failed["status"], "failed")
        self.assertTrue(any("hash" in item for item in failed["errors"]))


if __name__ == "__main__":
    unittest.main()
