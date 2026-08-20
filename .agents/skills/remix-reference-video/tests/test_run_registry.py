from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.run_registry import RunRegistry, RunRegistryError
from remix_reference_video.storage import TaskStorage, atomic_write_json
from tests.frozen_run_fixture import write_frozen_run_fixture


class RunRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(); self.addCleanup(self._temporary.cleanup)
        self.workspace = Path(self._temporary.name).resolve(); self.task = self.workspace / "work" / "cold"; self.task.mkdir(parents=True)
        TaskStorage(self.task).initialize_state({"execution_mode":"track-b-production","run_id":"run-1","state_revision":0,"active_stage":"gate1","active_command":None,"stage_status":{},"gate_status":{},"decisions":[],"artifacts":{},"blockers":[],"cache_summary":{}})
        write_frozen_run_fixture(self.task)
        self.registry = RunRegistry(self.workspace)

    def test_explicit_registration_and_restart_resolution(self) -> None:
        record = self.registry.register(self.task)
        self.assertEqual(record["run_id"], "run-1")
        self.assertEqual(record["pair_role"], "cold")
        restarted = RunRegistry(self.workspace)
        self.assertEqual(restarted.resolve("run-1"), self.task)
        with self.assertRaisesRegex(RunRegistryError, "already registered"):
            restarted.register(self.task)

    def test_symlink_escape_and_frozen_hash_drift_are_rejected(self) -> None:
        self.registry.register(self.task)
        marker = self.task / "g_b_frozen_input_snapshot.json"
        value = json.loads(marker.read_text(encoding="utf-8"))
        atomic_write_json(marker, {**value, "reference_sha256":"b"*64})
        with self.assertRaisesRegex(RunRegistryError, "stale|hash"):
            self.registry.resolve("run-1")
        link = self.workspace / "link"; link.symlink_to(self.task, target_is_directory=True)
        with self.assertRaisesRegex(RunRegistryError, "symlink"):
            RunRegistry(self.workspace).register(link)

    def test_repair_is_explicit_revisioned_and_audited(self) -> None:
        first = self.registry.register(self.task)
        moved = self.workspace / "work" / "cold-moved"; self.task.rename(moved)
        repaired = self.registry.repair("run-1", moved, expected_registry_revision=first["registry_revision"], actor="owner-a")
        self.assertEqual(repaired["task_dir"], str(moved))
        self.assertEqual(repaired["audit_history"][-1]["action"], "repair")

    def test_registry_accepts_versioned_nested_asset_snapshot(self) -> None:
        assets = self.task / "fixture-assets"
        original = assets / "asset.mp4"
        nested = assets / "products" / "asset.mp4"
        nested.parent.mkdir()
        original.rename(nested)
        marker = self.task / "g_b_frozen_input_snapshot.json"
        value = json.loads(marker.read_text(encoding="utf-8"))
        value["asset_snapshot_contract_version"] = "relative_path_v1"
        value["asset_snapshot"] = {"products/asset.mp4": value["asset_snapshot"]["asset.mp4"]}
        atomic_write_json(marker, value)
        self.assertEqual(self.registry.register(self.task)["run_id"], "run-1")

    def test_registry_rejects_nested_asset_without_contract_marker(self) -> None:
        marker = self.task / "g_b_frozen_input_snapshot.json"
        value = json.loads(marker.read_text(encoding="utf-8"))
        value["asset_snapshot"] = {"products/asset.mp4": next(iter(value["asset_snapshot"].values()))}
        atomic_write_json(marker, value)
        with self.assertRaisesRegex(RunRegistryError, "invalid|direct child"):
            self.registry.register(self.task)


if __name__ == "__main__": unittest.main()
