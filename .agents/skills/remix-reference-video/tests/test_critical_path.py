from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from remix_reference_video.critical_path import CriticalPathCollector, CriticalPathError
from remix_reference_video.orchestrator import creative_dag, default_dag
from remix_reference_video.storage import atomic_write_json


class CriticalPathTests(unittest.TestCase):
    def _metrics(self):
        return [{"execution_stage_id": node.node_id, "attempt_id": node.node_id, "status": "succeeded", "wall_seconds": 1.0, "cache_status": "miss"} for node in default_dag() if node.node_id not in {"init", "archive-approved"}]

    def test_parallel_roots_and_terminal_path(self):
        result = CriticalPathCollector().collect(self._metrics())
        self.assertEqual(result["measurement_status"], "measured")
        self.assertEqual(result["seconds"], 23.0)
        self.assertEqual(result["critical_path_nodes"][-1], "build-gate5-package")

    def test_missing_node_is_not_measured(self):
        result = CriticalPathCollector().collect(self._metrics()[:-1])
        self.assertEqual(result["measurement_status"], "not_measured")
        self.assertIn("build-gate5-package", result["missing_stage_ids"])

    def test_duplicate_attempt_is_rejected(self):
        rows = self._metrics(); rows.append(dict(rows[0]))
        with self.assertRaises(CriticalPathError):
            CriticalPathCollector().collect(rows)

    def test_task_selected_creative_dag_includes_creative_nodes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            atomic_write_json(root / "g_b_frozen_input_snapshot.json", {"creative_contract_version": "creative_contract_v1"})
            rows = [
                {"execution_stage_id": node.node_id, "attempt_id": node.node_id, "status": "succeeded", "wall_seconds": 1.0, "cache_status": "miss"}
                for node in creative_dag() if node.node_id not in {"init", "archive-approved"}
            ]
            result = CriticalPathCollector(task_root=root).collect(rows)
            self.assertEqual(result["measurement_status"], "measured")
            self.assertIn("generate-script-candidates", result["critical_path_nodes"])
            self.assertIn("build-final-content-diagnostic", result["critical_path_nodes"])


if __name__ == "__main__":
    unittest.main()
