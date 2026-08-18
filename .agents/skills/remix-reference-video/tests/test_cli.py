from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from remix_reference_video.cli import (
    _gb_pair_status,
    _pair_side_complete,
    _pair_side_halted,
    _pending_pair_gate,
    _production_runner,
    main,
)
from remix_reference_video.production_runtime import ProductionRuntimeConfig
from remix_reference_video.storage import TaskStorage, atomic_write_json
from tests.frozen_run_fixture import write_frozen_run_fixture


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

    def test_production_runner_factory_registers_real_native_dag(self) -> None:
        task = self.workspace / "work" / "real-task"
        task.mkdir()
        reference = task / "reference.mp4"
        reference.write_bytes(b"reference")
        assets = self.workspace / "assets"
        assets.mkdir()
        brief = task / "project_brief.yaml"
        brief.write_text("{}", encoding="utf-8")
        profiles = task / "asset_profiles.json"
        profiles.write_text('{"asset_profiles": []}', encoding="utf-8")
        client = task / "tts_client.py"
        client.write_text("# fixture", encoding="utf-8")

        runner = _production_runner(
            task,
            reference,
            asset_root=assets,
            brief_path=brief,
            asset_profiles_path=profiles,
            cache_path=task / "cache" / "assets.sqlite3",
            doubao_client_script=client,
        )

        self.assertIn("build-production-script", runner.adapters)
        self.assertIn("generate-voice", runner.adapters)
        self.assertIn("render-final", runner.adapters)

    def test_workbench_register_run_command_is_explicit_and_restart_readable(self) -> None:
        TaskStorage(self.task).initialize_state({"execution_mode":"track-b-production","run_id":"cli-run","state_revision":0,"active_stage":None,"active_command":None,"stage_status":{},"gate_status":{},"decisions":[],"artifacts":{},"blockers":[],"cache_summary":{}})
        write_frozen_run_fixture(self.task, pair_role="cold")

        code, stdout, _ = self.invoke("workbench-register-run", "--workspace-root", str(self.workspace), "--task-dir", str(self.task), "--json")

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["run_id"], "cli-run")
        self.assertTrue((self.workspace / "workbench/run_registry.json").is_file())

    def test_workbench_open_session_supports_cli_only_recovery(self) -> None:
        TaskStorage(self.task).initialize_state({"execution_mode":"track-b-production","run_id":"cli-run","state_revision":0,"active_stage":None,"active_command":None,"stage_status":{},"gate_status":{"gate5":"awaiting_user"},"decisions":[],"artifacts":{},"blockers":[],"cache_summary":{}})
        package_dir = self.task / "gate_review_packages"
        package_dir.mkdir()
        atomic_write_json(package_dir / "gate5.json", {"gate_id":"gate5","run_id":"cli-run","state_revision":0,"input_hashes":{}})

        code, stdout, _ = self.invoke(
            "workbench-open-session",
            "--task-dir", str(self.task),
            "--gate", "gate5",
            "--actor", "operator-a",
            "--json",
        )

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["actor"], "operator-a")
        self.assertEqual(payload["review_identity"]["gate_id"], "gate5")
        self.assertTrue((self.task / "workbench" / "sessions" / f"{payload['session_id']}.json").is_file())

    def test_workbench_serve_rejects_non_loopback_before_server_start(self) -> None:
        code, stdout, _ = self.invoke("workbench-serve", "--workspace-root", str(self.workspace), "--actor", "operator-a", "--host", "0.0.0.0", "--json")

        self.assertEqual(code, 2)
        self.assertIn("loopback", json.loads(stdout)["error"])

    def test_runtime_config_rejects_secret_fields_before_task_state_write(self) -> None:
        task = self.workspace / "work" / "config-task"
        task.mkdir()
        config = task / "production_runtime_config.json"
        config.write_text(
            json.dumps({"artifact_type": "production_runtime_config", "api_key": "secret"}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "secret"):
            ProductionRuntimeConfig.from_file(config)

    def test_production_status_alias_matches_status_projection(self) -> None:
        state = {
            "run_id": "production-alias",
            "execution_mode": "track-b-production",
            "state_revision": 4,
            "gate_status": {"gate5": "awaiting_user"},
        }
        (self.task / "pipeline_state.json").write_text(json.dumps(state), encoding="utf-8")
        status_code, status_stdout, _ = self.invoke(
            "status", "--task-dir", str(self.task), "--json"
        )
        alias_code, alias_stdout, _ = self.invoke(
            "production-status", "--task-dir", str(self.task), "--json"
        )
        self.assertEqual(status_code, 0)
        self.assertEqual(alias_code, 0)
        self.assertEqual(json.loads(alias_stdout), json.loads(status_stdout))

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
        self.assertEqual(cold["implementation_version"], "asset-index-v2")
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

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
    def test_isolated_production_fixture_runs_to_gate1_and_resume_waits(self) -> None:
        source = self.workspace / "source.mp4"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                "-i", "color=c=red:s=160x240:r=10:d=0.4", "-f", "lavfi", "-i",
                "color=c=blue:s=160x240:r=10:d=0.4", "-filter_complex",
                "[0:v][1:v]concat=n=2:v=1:a=0[outv]", "-map", "[outv]", "-c:v",
                "libx264", "-pix_fmt", "yuv420p", str(source),
            ],
            check=True,
        )
        task = self.workspace / "work" / "production-fixture"
        with patch("remix_reference_video.cli._require_track_b_unlocked"):
            init_code, _, _ = self.invoke(
                "init", "--workspace-root", str(self.workspace), "--task-dir", str(task),
                "--reference", str(source), "--json",
            )
            copied = task / source.name
            run_code, run_stdout, _ = self.invoke(
                "run", "--task-dir", str(task), "--reference", str(copied), "--json"
            )
            before_resume = {
                path.relative_to(task): path.read_bytes()
                for path in task.rglob("*")
                if path.is_file()
            }
            status_code, status_stdout, _ = self.invoke(
                "status", "--task-dir", str(task), "--json"
            )
            audit_code, audit_stdout, _ = self.invoke(
                "audit", "--task-dir", str(task), "--json"
            )
            resume_code, resume_stdout, _ = self.invoke(
                "resume", "--task-dir", str(task), "--reference", str(copied), "--json"
            )

        self.assertEqual(init_code, 0)
        self.assertEqual(run_code, 3)
        self.assertEqual(json.loads(run_stdout)["status"], "awaiting_user")
        self.assertEqual(status_code, 0)
        self.assertEqual(json.loads(status_stdout)["gate_status"], "awaiting_user")
        self.assertEqual(audit_code, 0)
        self.assertEqual(json.loads(audit_stdout)["status"], "passed")
        self.assertEqual(resume_code, 3)
        self.assertEqual(json.loads(resume_stdout)["status"], "awaiting_user")
        state = TaskStorage(task).read_state()
        self.assertEqual(state["gate_status"]["gate1"], "awaiting_user")
        self.assertEqual(state["decisions"], [])
        self.assertEqual(
            before_resume,
            {
                path.relative_to(task): path.read_bytes()
                for path in task.rglob("*")
                if path.is_file()
            },
        )

    def test_gb_pair_requires_frozen_marker_before_creating_tasks(self) -> None:
        frozen = self.workspace / "frozen"
        assets = self.workspace / "assets"
        frozen.mkdir()
        assets.mkdir()
        cold = self.workspace / "cold"
        hot = self.workspace / "hot"
        pair = self.workspace / "pair"
        client = self.workspace / "tts.py"
        client.write_text("# client", encoding="utf-8")
        code, stdout, _ = self.invoke(
            "gb-pair",
            "--frozen-root", str(frozen),
            "--asset-root", str(assets),
            "--cold-task-dir", str(cold),
            "--hot-task-dir", str(hot),
            "--pair-root", str(pair),
            "--doubao-client", str(client),
            "--json",
        )
        self.assertEqual(code, 4)
        self.assertEqual(json.loads(stdout)["status"], "blocked")
        self.assertFalse(cold.exists())
        self.assertFalse(hot.exists())

    def test_gb_pair_waits_for_gate5_package_before_requesting_approval(self) -> None:
        state = {"gate_status": {"gate5": "awaiting_user"}}

        self.assertIsNone(_pending_pair_gate(self.task, state))
        package = self.task / "gate_review_packages" / "gate5.json"
        package.parent.mkdir()
        package.write_text("{}\n", encoding="utf-8")

        self.assertEqual(_pending_pair_gate(self.task, state), "gate5")

    def test_gb_pair_ignores_aggregate_gate_wait_states(self) -> None:
        state = {
            "gate_status": {
                "gate3": "awaiting_user",
                "gate4": "awaiting_user",
            }
        }

        self.assertIsNone(_pending_pair_gate(self.task, state))

    def test_gb_pair_side_is_complete_at_approved_gate5(self) -> None:
        self.assertTrue(
            _pair_side_complete({"gate_status": {"gate5": "approved"}})
        )
        self.assertFalse(
            _pair_side_complete({"gate_status": {"gate5": "awaiting_user"}})
        )

    def test_gb_pair_side_stops_at_preflight_blocker(self) -> None:
        self.assertTrue(
            _pair_side_halted(
                {"gate_status": {"gate4_pre_generation": "blocked"}}
            )
        )
        self.assertFalse(
            _pair_side_halted(
                {"gate_status": {"gate4_pre_generation": "not_ready"}}
            )
        )

    def test_gb_pair_status_reports_hot_gate_wait(self) -> None:
        status, _ = _gb_pair_status(
            {"status": "succeeded", "gate_status": {"gate5": "approved"}},
            {"status": "awaiting_user", "gate_status": {"gate1": "awaiting_user"}},
        )

        self.assertEqual(status, "awaiting_user")

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
