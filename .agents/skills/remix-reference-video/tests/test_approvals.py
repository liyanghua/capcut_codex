from __future__ import annotations

import hashlib
import contextlib
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from remix_reference_video.approvals import ApprovalError, ApprovalService
from remix_reference_video.cli import main
from remix_reference_video.storage import TaskStorage, atomic_write_json


class ApprovalServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.store = TaskStorage(self.root)
        self.store.initialize_state(
            {
                "execution_mode": "track-b-production",
                "run_id": "run-1",
                "state_revision": 0,
                "active_stage": "performance_proven_video",
                "active_command": None,
                "stage_status": {},
                "gate_status": {
                    "gate1": "awaiting_user",
                    "gate2": "not_ready",
                    "gate3_material_selection": "not_ready",
                    "gate3_evidence_closure": "not_ready",
                    "gate3": "not_ready",
                    "gate4_pre_generation": "not_ready",
                    "gate4_post_generation": "not_ready",
                    "gate4": "not_ready",
                    "gate5": "not_ready",
                },
                "decisions": [],
                "artifacts": {},
                "blockers": [],
                "cache_summary": {},
            }
        )
        self.service = ApprovalService(self.store)

    @staticmethod
    def sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def write_package(self, gate: str, **overrides: object) -> tuple[Path, str]:
        artifact = self.root / "recipe.json"
        artifact.write_text('{"recipe":1}\n', encoding="utf-8")
        package: dict[str, object] = {
            "run_id": "run-1",
            "gate_id": gate,
            "created_at": "2026-08-15T12:00:00Z",
            "state_revision": self.store.read_state()["state_revision"],
            "input_hashes": {"recipe.json": self.sha256(artifact)},
        }
        package.update(overrides)
        path = self.root / "gate_review_packages" / f"{gate}.json"
        atomic_write_json(path, package)
        return path, self.sha256(path)

    def write_decision(self, **overrides: object) -> Path:
        decision: dict[str, object] = {
            "decision": "approved",
            "scope_type": "artifact_set",
            "scope_ids": ["recipe.json"],
            "strategy": {},
        }
        decision.update(overrides)
        path = self.root / "decision.json"
        atomic_write_json(path, decision)
        return path

    def approve(self, gate: str = "gate1", **package_overrides: object) -> dict[str, object]:
        _, digest = self.write_package(gate, **package_overrides)
        return self.service.approve(
            gate_id=gate,
            review_package_hash=digest,
            decision_file=self.write_decision(),
            actor="owner@example.test",
        )

    def test_approval_uses_trusted_time_and_current_package_hash(self) -> None:
        result = self.approve()

        self.assertEqual(result["decision"], "approved")
        self.assertEqual(self.store.read_state()["gate_status"]["gate1"], "approved")
        approved_at = datetime.fromisoformat(str(result["approved_at"]).replace("Z", "+00:00"))
        self.assertEqual(approved_at.tzinfo, UTC)

    def test_rejects_hash_mismatch_stale_revision_and_cross_task_package(self) -> None:
        path, digest = self.write_package("gate1")
        decision = self.write_decision()
        with self.assertRaisesRegex(ApprovalError, "hash"):
            self.service.approve(
                gate_id="gate1",
                review_package_hash="0" * 64,
                decision_file=decision,
                actor="owner",
            )

        atomic_write_json(path, read_json(path) | {"state_revision": 9})
        with self.assertRaisesRegex(ApprovalError, "revision"):
            self.service.approve(
                gate_id="gate1",
                review_package_hash=self.sha256(path),
                decision_file=decision,
                actor="owner",
            )

        atomic_write_json(path, read_json(path) | {"state_revision": 0, "run_id": "other"})
        with self.assertRaisesRegex(ApprovalError, "run"):
            self.service.approve(
                gate_id="gate1",
                review_package_hash=self.sha256(path),
                decision_file=decision,
                actor="owner",
            )

    def test_gate3_summary_requires_both_substates(self) -> None:
        state = self.store.update_state(
            lambda current: current
            | {
                "gate_status": current["gate_status"]
                | {
                    "gate1": "approved",
                    "gate2": "approved",
                    "gate3_material_selection": "awaiting_user",
                }
            }
        )
        self.approve("gate3_material_selection", state_revision=state["state_revision"])

        self.assertEqual(self.store.read_state()["gate_status"]["gate3"], "not_ready")

    def test_repeated_identical_approval_is_idempotent(self) -> None:
        path, digest = self.write_package("gate1")
        decision = self.write_decision()
        first = self.service.approve(
            gate_id="gate1",
            review_package_hash=digest,
            decision_file=decision,
            actor="owner",
        )
        second = self.service.approve(
            gate_id="gate1",
            review_package_hash=digest,
            decision_file=decision,
            actor="owner",
        )

        self.assertEqual(first["decision_id"], second["decision_id"])
        self.assertEqual(self.store.read_state()["state_revision"], 1)
        self.assertEqual(len(self.store.read_state()["decisions"]), 1)

    def test_gate4_pre_approval_promotes_script_with_tts_settings(self) -> None:
        candidate = self.root / "production_script_candidate.json"
        atomic_write_json(candidate, {"artifact_type": "production_script_candidate", "lines": []})
        state = self.store.update_state(
            lambda current: current
            | {
                "gate_status": current["gate_status"]
                | {
                    "gate1": "approved",
                    "gate2": "approved",
                    "gate3_material_selection": "approved",
                    "gate3_evidence_closure": "approved",
                    "gate3": "approved",
                    "gate4_pre_generation": "awaiting_user",
                }
            }
        )
        package, digest = self.write_package(
            "gate4_pre_generation",
            state_revision=state["state_revision"],
            input_hashes={"production_script_candidate.json": self.sha256(candidate)},
        )
        self.assertTrue(package.is_file())
        decision = self.write_decision(
            scope_ids=["production_script_candidate.json"],
            strategy={
                "tts_settings": {
                    "provider": "doubao",
                    "model": "DOUBAO_AUDIO",
                    "voice": "female",
                    "speed_ratio": 1.0,
                }
            },
        )

        self.service.approve(
            gate_id="gate4_pre_generation",
            review_package_hash=digest,
            decision_file=decision,
            actor="owner",
        )

        approved = read_json(self.root / "approved_production_script.json")
        self.assertEqual(approved["artifact_type"], "approved_production_script")
        self.assertEqual(approved["tts_settings"]["provider"], "doubao")
        self.assertEqual(
            self.store.read_state()["gate_status"]["gate4_pre_generation"],
            "approved",
        )

    def test_approve_gate_cli_returns_structured_success(self) -> None:
        _, digest = self.write_package("gate1")
        decision = self.write_decision()
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            code = main(
                [
                    "approve-gate",
                    "--task-dir",
                    str(self.root),
                    "--gate",
                    "gate1",
                    "--review-package-hash",
                    digest,
                    "--decision-file",
                    str(decision),
                    "--actor",
                    "owner",
                    "--json",
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["decision"], "approved")


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


if __name__ == "__main__":
    unittest.main()
