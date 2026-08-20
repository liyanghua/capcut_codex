from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.artifact_validator import ArtifactValidator
from remix_reference_video.project_initialization import (
    ProjectInitializationConflict,
    ProjectInitializationError,
    ProjectInitializationStore,
    claim_objects,
    validate_local_input_path,
)
from remix_reference_video.snapshot_schema_validator import SnapshotSchemaError, SnapshotSchemaValidator


SKILL_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = SKILL_ROOT / "schemas" / "v2-alpha.registry.schema.json"


def _draft(reference: Path, assets: Path, *, task_name: str = "tablemat-v2") -> dict[str, object]:
    return {
        "reference_path": str(reference),
        "asset_root": str(assets),
        "product_name": " 透明桌垫 ",
        "task_name": task_name,
        "platform": "抖音",
        "audience": "精致白领",
        "approved_claims": [" 防水  防油 ", "极简透明", "防水 防油"],
        "forbidden_claims": ["无"],
        "output": {"aspect_ratio": "9:16", "width": 1080, "height": 1920, "fps": 60},
        "voice": {"provider": "doubao", "speaker": "zh_female_gaolengyujie_uranus_bigtts", "speed": 1.0},
    }


class ProjectInitializationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.reference = self.workspace / "reference.mp4"
        self.reference.write_bytes(b"video")
        self.assets = self.workspace / "source"
        self.assets.mkdir()
        (self.assets / "asset.jpg").write_bytes(b"image")

    def test_claims_are_normalized_deduplicated_and_stable(self) -> None:
        first = claim_objects([" 防水  防油 ", "极简透明", "防水 防油"])
        second = claim_objects(["极简透明", "防水 防油"])
        self.assertEqual(first, second)
        self.assertEqual([row["text"] for row in first], sorted(["防水 防油", "极简透明"]))
        self.assertTrue(all(row["claim_id"].startswith("claim-") and len(row["claim_id"]) == 22 for row in first))

    def test_path_validation_rejects_relative_symlink_and_wrong_kind(self) -> None:
        with self.assertRaisesRegex(ProjectInitializationError, "absolute"):
            validate_local_input_path(Path("reference.mp4"), kind="reference")
        link = self.workspace / "reference-link.mp4"
        link.symlink_to(self.reference)
        with self.assertRaisesRegex(ProjectInitializationError, "symlink"):
            validate_local_input_path(link, kind="reference")
        with self.assertRaisesRegex(ProjectInitializationError, "directory"):
            validate_local_input_path(self.reference, kind="asset_root")

    def test_store_normalizes_draft_and_enforces_revision_and_idempotency(self) -> None:
        store = ProjectInitializationStore(self.workspace)
        created = store.save_draft(
            _draft(self.reference, self.assets),
            actor="local-operator",
            request_id="request-1",
            idempotency_key="draft-key-1",
        )
        replay = store.save_draft(
            _draft(self.reference, self.assets),
            actor="local-operator",
            request_id="request-1",
            idempotency_key="draft-key-1",
        )
        self.assertEqual(created, replay)
        self.assertEqual(created["draft_revision"], 1)
        self.assertEqual(created["approved_claims"], ["极简透明", "防水 防油"])
        self.assertEqual(created["forbidden_claims"], [])
        project_id = str(created["project_id"])
        with self.assertRaises(ProjectInitializationConflict):
            store.save_draft(
                {**_draft(self.reference, self.assets), "product_name": "changed"},
                project_id=project_id,
                expected_revision=0,
                actor="local-operator",
                request_id="request-2",
                idempotency_key="draft-key-2",
            )
        with self.assertRaisesRegex(ProjectInitializationConflict, "idempotency"):
            store.save_draft(
                {**_draft(self.reference, self.assets), "product_name": "conflict"},
                actor="local-operator",
                request_id="request-3",
                idempotency_key="draft-key-1",
            )
        audit = (self.workspace / "workbench" / "projects" / project_id / "audit.jsonl").read_text(encoding="utf-8")
        self.assertIn('"action": "draft.saved"', audit)

    def test_task_name_is_strict_and_reserved_once(self) -> None:
        store = ProjectInitializationStore(self.workspace)
        for invalid in ("Table Mat", "/tmp/task", "a_underscore"):
            with self.subTest(invalid):
                with self.assertRaises(ProjectInitializationError):
                    store.save_draft(
                        _draft(self.reference, self.assets, task_name=invalid),
                        actor="local-operator", request_id=f"r-{invalid}", idempotency_key=f"k-{invalid}",
                    )
        first = store.save_draft(
            _draft(self.reference, self.assets), actor="local-operator", request_id="reserve-1", idempotency_key="reserve-1"
        )
        store.reserve_task_root(str(first["project_id"]), date="2026-08-20")
        second = store.save_draft(
            _draft(self.reference, self.assets), actor="local-operator", request_id="reserve-2", idempotency_key="reserve-2"
        )
        with self.assertRaisesRegex(ProjectInitializationConflict, "task name"):
            store.reserve_task_root(str(second["project_id"]), date="2026-08-20")

    def test_stage0_artifacts_are_registered_as_non_authoritative(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        index = {row["artifact_type"]: row for row in registry["x-artifacts"]}
        for artifact_type in (
            "project_initialization_draft", "stage0_report",
            "material_evidence_requirements", "material_evidence_annotations",
        ):
            with self.subTest(artifact_type):
                self.assertIn(artifact_type, registry["properties"]["artifact_type"]["enum"])
                self.assertIs(index[artifact_type]["production_state_authority"], False)
                self.assertTrue((SKILL_ROOT / index[artifact_type]["schema_path"]).is_file())

    def test_non_authoritative_validator_rejects_approval_fields_recursively(self) -> None:
        store = ProjectInitializationStore(self.workspace)
        draft = store.save_draft(
            _draft(self.reference, self.assets), actor="local-operator", request_id="request-4", idempotency_key="draft-key-4"
        )
        project_root = self.workspace / "workbench" / "projects" / str(draft["project_id"])
        validator = ArtifactValidator(project_root)
        self.assertTrue(validator.validate_non_authoritative(project_root / "initialization_draft.json").valid)
        bad = json.loads((project_root / "initialization_draft.json").read_text(encoding="utf-8"))
        bad["voice"]["approval"] = "approved"
        (project_root / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
        result = validator.validate_non_authoritative(project_root / "bad.json")
        self.assertFalse(result.valid)
        self.assertTrue(any("approval" in error for error in result.errors))

    def test_draft_schema_is_strict(self) -> None:
        store = ProjectInitializationStore(self.workspace)
        draft = store.save_draft(
            _draft(self.reference, self.assets), actor="local-operator", request_id="request-5", idempotency_key="draft-key-5"
        )
        SnapshotSchemaValidator().assert_valid(draft, "project-initialization-draft.schema.json")
        with self.assertRaises(SnapshotSchemaError):
            SnapshotSchemaValidator().assert_valid({**draft, "decision": "approved"}, "project-initialization-draft.schema.json")


if __name__ == "__main__":
    unittest.main()
