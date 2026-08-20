from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.artifact_validator import ArtifactValidator
from remix_reference_video.project_initialization import (
    ProjectInitializationConflict,
    ProjectInitializationError,
    ProjectInitializationStore,
    claim_objects,
    pick_local_input_path,
    validate_local_input_path,
)
from remix_reference_video.runtime_resolver import RuntimeResolver, RuntimeUnavailable
from remix_reference_video.storage import read_json_object
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

    def test_native_picker_uses_fixed_macos_scripts_and_handles_cancel(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []

        def selected(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, stdout=str(self.reference) + "\n", stderr="")

        result = pick_local_input_path("reference_video", runner=selected, platform_name="darwin")
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["path"], str(self.reference))
        self.assertEqual(calls[0][0][0], "/usr/bin/osascript")
        self.assertNotIn(str(self.reference), calls[0][0])
        self.assertFalse(calls[0][1].get("shell", True))

        def cancelled(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="User canceled. (-128)\n")

        self.assertEqual(
            pick_local_input_path("asset_directory", runner=cancelled, platform_name="darwin")["status"],
            "cancelled",
        )
        self.assertEqual(pick_local_input_path("asset_directory", platform_name="linux")["status"], "unavailable")
        with self.assertRaisesRegex(ProjectInitializationError, "picker mode"):
            pick_local_input_path("arbitrary", runner=selected, platform_name="darwin")

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

    def test_stage0_builds_only_private_candidate_and_technical_profiles(self) -> None:
        store = ProjectInitializationStore(self.workspace)
        draft = store.save_draft(
            _draft(self.reference, self.assets), actor="local-operator", request_id="stage0-draft", idempotency_key="stage0-draft"
        )
        report = store.run_stage0(
            str(draft["project_id"]), request_id="stage0-run", idempotency_key="stage0-run",
            actor="local-operator", probe=lambda _path, media_type: {
                "media_type": media_type, "width": 1080, "height": 1920,
                "duration_seconds": None, "frame_rate": None, "has_audio": False,
            },
        )
        self.assertEqual(report["status"], "ready")
        project = self.workspace / "workbench" / "projects" / str(draft["project_id"])
        candidate = project / "stage0-candidate"
        self.assertEqual(len(list(candidate.glob("reference-*"))), 1)
        profiles = read_json_object(candidate / "asset_profiles.json")["asset_profiles"]
        self.assertEqual(len(profiles), 1)
        for forbidden in ("product_type", "semantic_tags", "action_tags", "scores", "claims"):
            self.assertNotIn(forbidden, profiles[0])
        for forbidden_path in ("pipeline_state.json", "gate_review_packages", "voice", "remix.mp4"):
            self.assertFalse((project / forbidden_path).exists())
            self.assertFalse((candidate / forbidden_path).exists())

    def test_stage0_cancellation_cleans_staging_and_does_not_publish_candidate(self) -> None:
        store = ProjectInitializationStore(self.workspace)
        draft = store.save_draft(
            _draft(self.reference, self.assets), actor="local-operator", request_id="cancel-draft", idempotency_key="cancel-draft"
        )
        report = store.run_stage0(
            str(draft["project_id"]), request_id="cancel-run", idempotency_key="cancel-run",
            actor="local-operator", probe=lambda _path, _kind: {}, cancel_check=lambda: True,
        )
        self.assertEqual(report["status"], "cancelled")
        project = self.workspace / "workbench" / "projects" / str(draft["project_id"])
        self.assertFalse((project / "stage0-candidate").exists())
        self.assertEqual(list((project / ".staging").glob("*")), [])

    def test_freeze_rehashes_inputs_and_writes_no_run_state(self) -> None:
        store = ProjectInitializationStore(self.workspace)
        draft = store.save_draft(
            _draft(self.reference, self.assets), actor="local-operator", request_id="freeze-draft", idempotency_key="freeze-draft"
        )
        report = store.run_stage0(
            str(draft["project_id"]), request_id="freeze-stage0", idempotency_key="freeze-stage0",
            actor="local-operator", probe=lambda _path, media_type: {"media_type": media_type, "width": 100, "height": 100},
        )
        frozen = store.freeze(
            str(draft["project_id"]), expected_draft_revision=1,
            expected_report_sha256=str(report["report_sha256"]), actor="local-operator",
            request_id="freeze", idempotency_key="freeze",
            date="2026-08-20",
        )
        root = Path(str(frozen["frozen_root"]))
        marker = read_json_object(root / "g_b_frozen_input_snapshot.json")
        brief = read_json_object(root / "project_brief.json")
        self.assertEqual(marker["creative_contract_version"], "creative_contract_v1")
        self.assertEqual(marker["asset_snapshot_contract_version"], "relative_path_v1")
        self.assertEqual(brief["approved_claims"], claim_objects(["极简透明", "防水 防油"]))
        self.assertFalse((root / "pipeline_state.json").exists())
        self.assertFalse((root.parent / "cold").exists())
        self.assertFalse((root.parent / "hot").exists())

    def test_freeze_rejects_changed_source(self) -> None:
        store = ProjectInitializationStore(self.workspace)
        draft = store.save_draft(
            _draft(self.reference, self.assets), actor="local-operator", request_id="changed-draft", idempotency_key="changed-draft"
        )
        report = store.run_stage0(
            str(draft["project_id"]), request_id="changed-stage0", idempotency_key="changed-stage0",
            actor="local-operator", probe=lambda _path, media_type: {"media_type": media_type},
        )
        (self.assets / "asset.jpg").write_bytes(b"changed")
        with self.assertRaisesRegex(ProjectInitializationConflict, "input changed"):
            store.freeze(
                str(draft["project_id"]), expected_draft_revision=1,
                expected_report_sha256=str(report["report_sha256"]), actor="local-operator",
                request_id="changed-freeze", idempotency_key="changed-freeze", date="2026-08-20",
            )

    def test_start_cold_fails_before_pair_creation_when_runtime_unavailable(self) -> None:
        store = ProjectInitializationStore(self.workspace)
        draft = store.save_draft(
            _draft(self.reference, self.assets), actor="local-operator", request_id="runtime-draft", idempotency_key="runtime-draft"
        )
        report = store.run_stage0(
            str(draft["project_id"]), request_id="runtime-stage0", idempotency_key="runtime-stage0",
            actor="local-operator", probe=lambda _path, media_type: {"media_type": media_type},
        )
        store.freeze(
            str(draft["project_id"]), expected_draft_revision=1, expected_report_sha256=str(report["report_sha256"]),
            actor="local-operator", request_id="runtime-freeze", idempotency_key="runtime-freeze", date="2026-08-20",
        )
        result = store.start_cold(
            str(draft["project_id"]), actor="local-operator", request_id="runtime-start",
            idempotency_key="runtime-start", runtime_resolver=RuntimeResolver(self.workspace),
        )
        self.assertEqual(result["status"], "runtime_unavailable")
        task_root = self.workspace / "work" / "2026-08-20-tablemat-v2"
        self.assertFalse((task_root / "cold").exists())
        self.assertFalse((task_root / "hot").exists())


if __name__ == "__main__":
    unittest.main()
