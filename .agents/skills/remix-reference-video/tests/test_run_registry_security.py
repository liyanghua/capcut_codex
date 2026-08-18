from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from remix_reference_video.change_service import ChangeConflict, WorkbenchOrchestrator
from remix_reference_video.cli import run_gb_pair
from remix_reference_video.run_registry import RunRegistry, RunRegistryError
from remix_reference_video.storage import TaskStorage, atomic_write_json


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_source_contract(root: Path, *, pair_role: str | None) -> tuple[Path, Path]:
    assets = root.parent / "assets"
    assets.mkdir(exist_ok=True)
    asset = assets / "asset.mp4"
    asset.write_bytes(b"asset")
    reference = root / "reference-fixture.mp4"
    reference.write_bytes(b"reference")
    brief = root / "project_brief.json"
    atomic_write_json(brief, {"artifact_type": "project_brief"})
    profiles = root / "asset_profiles.json"
    atomic_write_json(profiles, {"artifact_type": "asset_profiles"})
    marker = {
        "artifact_type": "g_b_frozen_input_snapshot",
        "reference_sha256": _sha256(reference),
        "brief_sha256": _sha256(brief),
        "asset_profiles_sha256": _sha256(profiles),
        "asset_snapshot": {asset.name: _sha256(asset)},
        "approval_records": [],
    }
    if pair_role is not None:
        marker["pair_role"] = pair_role
    atomic_write_json(root / "g_b_frozen_input_snapshot.json", marker)
    return assets, reference


def _initialize_run(task: Path, run_id: str) -> None:
    TaskStorage(task).initialize_state(
        {
            "execution_mode": "track-b-production",
            "run_id": run_id,
            "state_revision": 0,
            "active_stage": None,
            "active_command": None,
            "stage_status": {},
            "gate_status": {},
            "decisions": [],
            "artifacts": {},
            "blockers": [],
            "cache_summary": {},
        }
    )


def _write_runtime_config(task: Path, assets: Path, reference: Path) -> None:
    client = task / "tts_client.py"
    client.write_text("# fixture\n", encoding="utf-8")
    (task / "cache").mkdir(exist_ok=True)
    atomic_write_json(
        task / "production_runtime_config.json",
        {
            "artifact_type": "production_runtime_config",
            "reference_path": reference.name,
            "asset_root": str(assets),
            "brief_path": "project_brief.json",
            "asset_profiles_path": "asset_profiles.json",
            "cache_path": "cache/assets.sqlite3",
            "doubao_client_script": client.name,
            "python_executable": sys.executable,
        },
    )


class RunRegistrySecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.workspace = Path(self._temporary.name).resolve()

    def test_minimal_marker_cannot_masquerade_as_gb_pair(self) -> None:
        task = self.workspace / "ordinary-track-b"
        task.mkdir()
        assets, reference = _write_source_contract(task, pair_role="cold")
        _initialize_run(task, "ordinary-run")
        _write_runtime_config(task, assets, reference)
        atomic_write_json(
            task / "g_b_frozen_input_snapshot.json",
            {
                "artifact_type": "g_b_frozen_input_snapshot",
                "pair_role": "cold",
                "reference_sha256": _sha256(reference),
            },
        )

        with self.assertRaisesRegex(RunRegistryError, "frozen input snapshot"):
            RunRegistry(self.workspace).register(task)

    def test_resume_rejects_legacy_minimal_registry_entry_before_runner(self) -> None:
        task = self.workspace / "ordinary-track-b"
        task.mkdir()
        _initialize_run(task, "ordinary-run")
        marker = task / "g_b_frozen_input_snapshot.json"
        atomic_write_json(
            marker,
            {
                "artifact_type": "g_b_frozen_input_snapshot",
                "pair_role": "cold",
                "reference_sha256": "a" * 64,
            },
        )
        registry_root = self.workspace / "workbench"
        registry_root.mkdir()
        atomic_write_json(
            registry_root / "run_registry.json",
            {
                "registry_revision": 1,
                "runs": {
                    "ordinary-run": {
                        "run_id": "ordinary-run",
                        "task_dir": str(task),
                        "execution_mode": "track-b-production",
                        "pair_role": "cold",
                        "g_b_frozen_input_snapshot_sha256": _sha256(marker),
                    }
                },
            },
        )

        called = False

        def forbidden(_: Path) -> object:
            nonlocal called
            called = True
            raise AssertionError("runner must not be constructed")

        with self.assertRaisesRegex(ChangeConflict, "frozen input snapshot"):
            WorkbenchOrchestrator(
                self.workspace, actor="operator-a", runner_factory=forbidden
            ).resume_job(run_id="ordinary-run", job_id="job-1")
        self.assertFalse(called)

    def test_registration_requires_runtime_config_and_live_source_hashes(self) -> None:
        task = self.workspace / "pair" / "cold"
        task.mkdir(parents=True)
        assets, reference = _write_source_contract(task, pair_role="cold")
        _initialize_run(task, "gb-cold-run")

        with self.assertRaisesRegex(RunRegistryError, "runtime config"):
            RunRegistry(self.workspace).register(task)

        _write_runtime_config(task, assets, reference)
        registry = RunRegistry(self.workspace)
        registry.register(task)
        (assets / "asset.mp4").write_bytes(b"changed")
        with self.assertRaisesRegex(RunRegistryError, "stale|hash"):
            registry.resolve("gb-cold-run")

    def test_gb_pair_registers_each_initialized_side(self) -> None:
        pair_root = self.workspace / "work" / "pair"
        frozen = self.workspace / "frozen"
        frozen.mkdir()
        assets, _ = _write_source_contract(frozen, pair_role=None)
        client = self.workspace / "tts.py"
        client.write_text("# fixture\n", encoding="utf-8")

        def fake_side(*, task_dir: Path, run_id: str, **_: object) -> dict[str, object]:
            _initialize_run(task_dir, run_id)
            return {
                "run_id": run_id,
                "status": "succeeded",
                "gate_status": {"gate5": "approved"},
                "exit_code": 0,
            }

        args = SimpleNamespace(
            frozen_root=frozen,
            asset_root=assets,
            cold_task_dir=pair_root / "cold",
            hot_task_dir=pair_root / "hot",
            pair_root=pair_root,
            doubao_client=client,
            python_executable=sys.executable,
            decision_dir=None,
            actor="owner-a",
            resume_existing=False,
        )
        with patch("remix_reference_video.cli._run_pair_side", side_effect=fake_side):
            result = run_gb_pair(args)

        registry = RunRegistry(pair_root)
        cold_run = str(result["cold"]["run_id"])
        hot_run = str(result["hot"]["run_id"])
        self.assertEqual(registry.resolve(cold_run), pair_root / "cold")
        self.assertEqual(registry.resolve(hot_run), pair_root / "hot")


if __name__ == "__main__":
    unittest.main()
