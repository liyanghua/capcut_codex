from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.cli import main
from remix_reference_video.storage import TaskStorage


FIXTURES = Path(__file__).parent / "fixtures"


class FastPathVerticalTest(unittest.TestCase):
    def test_fixture_stops_resumes_succeeds_then_fully_hits_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            task = workspace / "work" / "fast-path-v0-fixture"
            shutil.copytree(FIXTURES / "fast_path_task", task)
            plan = workspace / "fast_path_plan.json"
            shutil.copy2(FIXTURES / "fast_path_plan.json", plan)
            arguments = [
                "--workspace-root",
                str(workspace),
                "--plan",
                str(plan),
                "--json",
            ]

            first_code, first = self._invoke("fast", *arguments)
            self.assertEqual(first_code, 3)
            self.assertEqual(first["status"], "awaiting_user")

            store = TaskStorage(task)
            store.update_state(lambda state: self._approve_gate(state, "gate1"))
            resumed_code, resumed = self._invoke("resume", *arguments)
            cached_code, cached = self._invoke("resume", *arguments)

            self.assertEqual(resumed_code, 0)
            self.assertEqual(resumed["status"], "succeeded")
            self.assertEqual(cached_code, 0)
            self.assertEqual(cached["status"], "cache_hit")
            self.assertEqual((task / "recipe.json").read_text(), "reference-facts")
            self.assertEqual((task / "shot_blueprint.json").read_text(), "blueprint")

    @staticmethod
    def _invoke(*arguments: str) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(list(arguments))
        return exit_code, json.loads(output.getvalue())

    @staticmethod
    def _approve_gate(state: dict[str, object], gate_id: str) -> dict[str, object]:
        gate_status = state["gate_status"]
        fast_path = state["fast_path"]
        assert isinstance(gate_status, dict) and isinstance(fast_path, dict)
        gate_inputs = fast_path["gate_inputs"]
        assert isinstance(gate_inputs, dict)
        expected = gate_inputs[gate_id]
        assert isinstance(expected, dict)
        gate_status[gate_id] = "approved"
        decisions = state.setdefault("decisions", [])
        assert isinstance(decisions, list)
        decisions.append(
            {
                "gate_id": gate_id,
                "decision": "approved",
                "input_hashes": expected["output_hashes"],
            }
        )
        return state


if __name__ == "__main__":
    unittest.main()
