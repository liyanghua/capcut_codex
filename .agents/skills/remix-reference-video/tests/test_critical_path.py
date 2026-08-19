from __future__ import annotations

import unittest

from remix_reference_video.critical_path import CriticalPathCollector, CriticalPathError
from remix_reference_video.orchestrator import default_dag


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


if __name__ == "__main__":
    unittest.main()
