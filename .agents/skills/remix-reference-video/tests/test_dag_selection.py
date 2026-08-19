from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from remix_reference_video.orchestrator import (
    CREATIVE_DAG_VERSION,
    HARDENED_DAG_VERSION,
    LEGACY_DAG_VERSION,
    creative_dag,
    dag_for_task,
    dag_version_for_task,
    default_dag,
    legacy_dag,
)
from remix_reference_video.runner import ProductionRunner
from remix_reference_video.storage import atomic_write_json


class DagSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_three_way_matrix_uses_single_frozen_capability_marker(self) -> None:
        legacy = self.root / "legacy"
        legacy.mkdir()
        self.assertEqual(dag_version_for_task(legacy), LEGACY_DAG_VERSION)
        self.assertEqual(tuple(node.node_id for node in dag_for_task(legacy)), tuple(node.node_id for node in legacy_dag()))

        hardened = self.root / "hardened"
        hardened.mkdir()
        atomic_write_json(hardened / "content_baseline.json", {"narrative_contract_version": "narrative_contract_v1"})
        self.assertEqual(dag_version_for_task(hardened), HARDENED_DAG_VERSION)
        self.assertEqual(tuple(node.node_id for node in dag_for_task(hardened)), tuple(node.node_id for node in default_dag()))

        creative = self.root / "creative"
        creative.mkdir()
        atomic_write_json(creative / "g_b_frozen_input_snapshot.json", {"creative_contract_version": "creative_contract_v1"})
        self.assertEqual(dag_version_for_task(creative), CREATIVE_DAG_VERSION)
        self.assertEqual(tuple(node.node_id for node in dag_for_task(creative)), tuple(node.node_id for node in creative_dag()))

    def test_creative_marker_wins_over_legacy_state_and_is_not_silent(self) -> None:
        task = self.root / "task"
        task.mkdir()
        atomic_write_json(task / "g_b_frozen_input_snapshot.json", {"creative_contract_version": "creative_contract_v1"})
        atomic_write_json(task / "pipeline_state.json", {"production_dag_version": LEGACY_DAG_VERSION})
        self.assertEqual(dag_version_for_task(task), CREATIVE_DAG_VERSION)

    def test_initialize_persists_selected_dag_version(self) -> None:
        task = self.root / "initialize"
        task.mkdir()
        atomic_write_json(task / "g_b_frozen_input_snapshot.json", {"creative_contract_version": "creative_contract_v1"})
        state = ProductionRunner(task, ()).initialize(run_id="creative-run")
        self.assertEqual(state["production_dag_version"], CREATIVE_DAG_VERSION)


if __name__ == "__main__":
    unittest.main()
