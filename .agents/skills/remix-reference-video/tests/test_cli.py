from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from remix_reference_video.cli import main
from remix_reference_video.storage import TaskStorage


FIXTURE_STAGE = Path(__file__).parent / "fixtures" / "mock_stage.py"


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.workspace = Path(self._temporary.name).resolve()
        self.task = self.workspace / "work" / "fixture"
        self.task.mkdir(parents=True)
        (self.task / "input.txt").write_text("input", encoding="utf-8")

    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(list(arguments))
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def write_plan(self, *, fail: bool = False) -> Path:
        argv = [
            sys.executable,
            str(FIXTURE_STAGE),
            "--output",
            "result.json",
        ]
        if fail:
            argv = [sys.executable, str(FIXTURE_STAGE), "--exit-code", "9"]
        plan = {
            "task_root": "work/fixture",
            "execution_mode": "fast-path-v0",
            "stages": [
                {
                    "execution_stage_id": "fixture-stage",
                    "framework_stage_id": "performance_proven_video",
                    "argv": argv,
                    "inputs": ["input.txt"],
                    "outputs": ["result.json"],
                    "required_gates": [],
                    "stop_gate": None if fail else "gate1",
                    "timeout_seconds": 5,
                    "cache": True,
                }
            ],
        }
        path = self.workspace / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return path

    def test_fast_resume_status_and_audit_json_workflow(self) -> None:
        plan = self.write_plan()
        common = ("--workspace-root", str(self.workspace), "--plan", str(plan), "--json")

        fast_code, fast_stdout, _ = self.invoke("fast", *common)
        fast_result = json.loads(fast_stdout)
        self.assertEqual(fast_code, 3)
        self.assertEqual(fast_result["status"], "awaiting_user")

        store = TaskStorage(self.task)
        store.update_state(lambda state: self._approve_gate(state, "gate1"))
        gap_code, gap_stdout, _ = self.invoke(
            "audit", "--task-dir", str(self.task), "--json"
        )
        self.assertEqual(gap_code, 0)
        self.assertEqual(json.loads(gap_stdout)["status"], "passed_with_warnings")
        self.assertTrue(
            any("event" in warning for warning in json.loads(gap_stdout)["warnings"])
        )
        resumed_code, resumed_stdout, _ = self.invoke("resume", *common)
        cached_code, cached_stdout, _ = self.invoke("resume", *common)
        self.assertEqual(resumed_code, 0)
        self.assertEqual(json.loads(resumed_stdout)["status"], "cache_hit")
        self.assertEqual(cached_code, 0)
        self.assertEqual(json.loads(cached_stdout)["status"], "cache_hit")

        status_code, status_stdout, _ = self.invoke(
            "status", "--task-dir", str(self.task), "--json"
        )
        audit_code, audit_stdout, _ = self.invoke(
            "audit", "--task-dir", str(self.task), "--json"
        )
        self.assertEqual(status_code, 0)
        self.assertEqual(json.loads(status_stdout)["run_status"], "cache_hit")
        self.assertEqual(audit_code, 0)
        self.assertEqual(json.loads(audit_stdout)["status"], "passed")

    def test_status_and_audit_are_read_only_for_manual_contract_pilot(self) -> None:
        state = {
            "run_id": "manual-pilot",
            "execution_mode": "manual-contract-only",
            "current_stage": "final_review",
            "gate_status": {"gate5": "awaiting_user"},
        }
        (self.task / "pipeline_state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )
        before = {
            path.relative_to(self.task): path.read_bytes()
            for path in self.task.rglob("*")
            if path.is_file()
        }

        status_code, status_stdout, _ = self.invoke(
            "status", "--task-dir", str(self.task)
        )
        audit_code, audit_stdout, _ = self.invoke(
            "audit", "--task-dir", str(self.task), "--json"
        )

        after = {
            path.relative_to(self.task): path.read_bytes()
            for path in self.task.rglob("*")
            if path.is_file()
        }
        self.assertEqual(status_code, 0)
        self.assertIn("Gate gate5", status_stdout)
        self.assertEqual(audit_code, 0)
        self.assertEqual(json.loads(audit_stdout)["status"], "passed_with_warnings")
        self.assertEqual(before, after)

    def test_status_rejects_duplicate_state_keys(self) -> None:
        state_path = self.task / "pipeline_state.json"
        state_path.write_text(
            '{"run_id":"first","run_id":"second"}', encoding="utf-8"
        )

        exit_code, output, _ = self.invoke("status", "--task-dir", str(self.task), "--json")

        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(output)["status"], "invalid")

    def test_audit_reports_empty_non_object_stage_cache_without_traceback(self) -> None:
        TaskStorage(self.task).initialize_state(
            {
                "run_id": "fixture",
                "execution_mode": "fast-path-v0",
                "state_revision": 0,
                "gate_status": {},
            }
        )
        state = json.loads(
            (self.task / "pipeline_state.json").read_text(encoding="utf-8")
        )
        state["execution_mode"] = "fast-path-v0"
        state["fast_path"] = {"stage_cache": []}
        (self.task / "pipeline_state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )

        exit_code, stdout, _ = self.invoke(
            "audit", "--task-dir", str(self.task), "--json"
        )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 5)
        self.assertEqual(payload["status"], "failed")
        self.assertIn("stage_cache must be an object", payload["errors"])

    def test_audit_reports_non_string_gate_status_without_traceback(self) -> None:
        TaskStorage(self.task).initialize_state(
            {
                "run_id": "fixture",
                "execution_mode": "fast-path-v0",
                "state_revision": 0,
                "gate_status": {"gate1": []},
            }
        )

        exit_code, stdout, _ = self.invoke(
            "audit", "--task-dir", str(self.task), "--json"
        )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 5)
        self.assertEqual(payload["status"], "failed")
        self.assertIn("gate1 has invalid status []", payload["errors"])

    def test_audit_reports_non_string_execution_mode_without_traceback(self) -> None:
        TaskStorage(self.task).initialize_state(
            {
                "run_id": "fixture",
                "execution_mode": [],
                "state_revision": 0,
                "gate_status": {},
            }
        )

        exit_code, stdout, _ = self.invoke(
            "audit", "--task-dir", str(self.task), "--json"
        )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 5)
        self.assertEqual(payload["status"], "failed")
        self.assertIn("unsupported execution_mode", payload["errors"])

    def test_audit_rejects_approved_gate_without_hash_bound_decision(self) -> None:
        TaskStorage(self.task).initialize_state(
            {
                "run_id": "fixture",
                "execution_mode": "fast-path-v0",
                "state_revision": 0,
                "gate_status": {"gate1": "approved"},
                "decisions": [],
                "fast_path": {"gate_inputs": {}, "stage_cache": {}},
            }
        )

        exit_code, stdout, _ = self.invoke(
            "audit", "--task-dir", str(self.task), "--json"
        )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 5)
        self.assertIn("gate1 approval is not hash-bound", payload["errors"])

    def test_audit_rejects_nonmonotonic_event_state_revisions(self) -> None:
        store = TaskStorage(self.task)
        store.initialize_state(
            {
                "run_id": "fixture",
                "execution_mode": "fast-path-v0",
                "state_revision": 0,
                "gate_status": {},
            }
        )
        store.update_state(lambda state: state)
        store.update_state(lambda state: state)
        (self.task / "pipeline_events.jsonl").write_text(
            '{"sequence":1,"state_revision":2}\n'
            '{"sequence":2,"state_revision":1}\n',
            encoding="utf-8",
        )

        exit_code, stdout, _ = self.invoke(
            "audit", "--task-dir", str(self.task), "--json"
        )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 5)
        self.assertIn("event state_revision is not monotonic", payload["errors"])

    def test_index_assets_reports_cold_then_warm_cache(self) -> None:
        assets = self.workspace / "assets"
        assets.mkdir()
        (assets / "broken.jpg").write_bytes(b"")
        database = self.workspace / "cache" / "assets.sqlite3"
        arguments = (
            "index-assets",
            "--assets-root",
            str(assets),
            "--database",
            str(database),
            "--json",
        )

        cold_code, cold_stdout, _ = self.invoke(*arguments)
        warm_code, warm_stdout, _ = self.invoke(*arguments)

        cold = json.loads(cold_stdout)
        warm = json.loads(warm_stdout)
        self.assertEqual(cold_code, 0)
        self.assertEqual(cold["supported_files"], 1)
        self.assertEqual(cold["unreadable_files"], 1)
        self.assertEqual(warm_code, 0)
        self.assertEqual(warm["cache_hits"], 1)
        self.assertEqual(warm["probed_contents"], 0)

    def test_index_assets_reports_missing_ffprobe_as_runtime_failure(self) -> None:
        assets = self.workspace / "assets"
        assets.mkdir()
        database = self.workspace / "cache" / "assets.sqlite3"

        with patch("remix_reference_video.asset_index.shutil.which", return_value=None):
            exit_code, stdout, _ = self.invoke(
                "index-assets",
                "--assets-root",
                str(assets),
                "--database",
                str(database),
                "--json",
            )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 5)
        self.assertEqual(payload["status"], "failed")
        self.assertIn("FFprobe executable not found", payload["error"])

    def test_index_assets_reports_corrupt_database_as_runtime_failure(self) -> None:
        assets = self.workspace / "assets"
        assets.mkdir()
        database = self.workspace / "cache" / "assets.sqlite3"
        database.parent.mkdir()
        database.write_bytes(b"not a sqlite database")

        exit_code, stdout, _ = self.invoke(
            "index-assets",
            "--assets-root",
            str(assets),
            "--database",
            str(database),
            "--json",
        )

        payload = json.loads(stdout)
        self.assertEqual(exit_code, 5)
        self.assertEqual(payload["status"], "failed")

    def test_cli_returns_stable_validation_block_and_failure_codes(self) -> None:
        invalid = self.workspace / "invalid.json"
        invalid.write_text("{}", encoding="utf-8")
        invalid_code, _, _ = self.invoke(
            "fast",
            "--workspace-root",
            str(self.workspace),
            "--plan",
            str(invalid),
        )
        self.assertEqual(invalid_code, 2)

        failed_plan = self.write_plan(fail=True)
        failed_code, failed_stdout, _ = self.invoke(
            "fast",
            "--workspace-root",
            str(self.workspace),
            "--plan",
            str(failed_plan),
            "--json",
        )
        self.assertEqual(failed_code, 5)
        self.assertEqual(json.loads(failed_stdout)["error_code"], "STAGE_COMMAND_FAILED")

        manual = json.loads((self.task / "pipeline_state.json").read_text())
        manual["execution_mode"] = "manual-contract-only"
        (self.task / "pipeline_state.json").write_text(json.dumps(manual))
        blocked_code, blocked_stdout, _ = self.invoke(
            "resume",
            "--workspace-root",
            str(self.workspace),
            "--plan",
            str(failed_plan),
            "--json",
        )
        self.assertEqual(blocked_code, 4)
        self.assertEqual(json.loads(blocked_stdout)["error_code"], "MANUAL_CONTRACT_ONLY")

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
