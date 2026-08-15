from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.cli import main


SKILL_ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


class TrackBLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.workspace = Path(self._temporary.name).resolve()

    def invoke(self, *arguments: str) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(list(arguments))
        return code, json.loads(stdout.getvalue())

    def test_track_b_production_plan_is_rejected_while_manifest_locked(self) -> None:
        task = self.workspace / "work" / "track-b-fixture"
        task.mkdir(parents=True)
        (task / "input.txt").write_text("input", encoding="utf-8")
        shutil.copy2(FIXTURES / "mock_stage.py", task / "mock_stage.py")
        plan = self.workspace / "track_b_plan.json"
        shutil.copy2(FIXTURES / "track_b_plan.json", plan)
        manifest_before = (SKILL_ROOT / "manifest.json").read_bytes()

        code, payload = self.invoke(
            "fast",
            "--workspace-root",
            str(self.workspace),
            "--plan",
            str(plan),
            "--json",
        )

        self.assertEqual(code, 2)
        self.assertIn("Track B", str(payload.get("error")))
        self.assertFalse((task / "pipeline_state.json").exists())
        self.assertEqual(manifest_before, (SKILL_ROOT / "manifest.json").read_bytes())

    def test_fast_path_fixture_remains_executable(self) -> None:
        task = self.workspace / "work" / "fast-path-v0-fixture"
        shutil.copytree(FIXTURES / "fast_path_task", task)
        plan = self.workspace / "fast_path_plan.json"
        shutil.copy2(FIXTURES / "fast_path_plan.json", plan)

        code, payload = self.invoke(
            "fast", "--workspace-root", str(self.workspace), "--plan", str(plan), "--json"
        )

        self.assertEqual(code, 3)
        self.assertEqual(payload["status"], "awaiting_user")

    def test_manual_contract_pilot_fast_and_resume_are_write_free(self) -> None:
        task = self.workspace / "work" / "pilot"
        task.mkdir(parents=True)
        (task / "pipeline_state.json").write_text(
            json.dumps(
                {
                    "run_id": "pilot",
                    "execution_mode": "manual-contract-only",
                    "state_revision": 7,
                    "gate_status": {"gate5": "awaiting_user"},
                }
            ),
            encoding="utf-8",
        )
        plan = self.workspace / "pilot_plan.json"
        plan.write_text(
            json.dumps(
                {
                    "task_root": "work/pilot",
                    "execution_mode": "fast-path-v0",
                    "stages": [
                        {
                            "execution_stage_id": "pilot-stage",
                            "framework_stage_id": "performance_proven_video",
                            "argv": ["python3", "mock_stage.py", "--output", "result.json"],
                            "inputs": ["input.txt"],
                            "outputs": ["result.json"],
                            "required_gates": [],
                            "stop_gate": None,
                            "timeout_seconds": 10,
                            "cache": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        before = {
            path.relative_to(task): path.read_bytes()
            for path in task.rglob("*")
            if path.is_file()
        }

        for command in ("fast", "resume"):
            code, payload = self.invoke(
                command,
                "--workspace-root",
                str(self.workspace),
                "--plan",
                str(plan),
                "--json",
            )
            self.assertEqual(code, 4)
            self.assertEqual(payload.get("error_code"), "MANUAL_CONTRACT_ONLY")

        after = {
            path.relative_to(task): path.read_bytes()
            for path in task.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
