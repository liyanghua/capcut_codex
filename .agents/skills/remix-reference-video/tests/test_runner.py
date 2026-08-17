from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import multiprocessing
import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from remix_reference_video import ExecutionPlan
from remix_reference_video.approvals import ApprovalService
from remix_reference_video.runner import FastPathRunner, ProductionRunner
from remix_reference_video.storage import TaskStorage


FIXTURE_STAGE = Path(__file__).parent / "fixtures" / "mock_stage.py"


def _run_plan_in_child(plan: ExecutionPlan, queue: multiprocessing.Queue[dict[str, object]]) -> None:
    queue.put(dataclasses.asdict(FastPathRunner(plan).run()))


class FastPathRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.workspace_root = Path(self._temporary.name).resolve()
        self.task_root = self.workspace_root / "work" / "fixture"
        self.task_root.mkdir(parents=True)
        (self.task_root / "input.txt").write_text("input-v1", encoding="utf-8")

    def stage(self, **overrides: object) -> dict[str, object]:
        value: dict[str, object] = {
            "execution_stage_id": "stage-one",
            "framework_stage_id": "performance_proven_video",
            "argv": [
                sys.executable,
                str(FIXTURE_STAGE),
                "--output",
                "first.json",
                "--counter",
                "calls.log",
            ],
            "inputs": ["input.txt"],
            "outputs": ["first.json"],
            "required_gates": [],
            "stop_gate": None,
            "timeout_seconds": 5,
            "cache": True,
        }
        value.update(overrides)
        return value

    def plan(self, stages: list[dict[str, object]]) -> ExecutionPlan:
        return ExecutionPlan.from_object(
            {
                "task_root": "work/fixture",
                "execution_mode": "fast-path-v0",
                "stages": stages,
            },
            workspace_root=self.workspace_root,
        )

    @staticmethod
    def approve_gate(state: dict[str, object], gate_id: str) -> dict[str, object]:
        updated = copy.deepcopy(state)
        gate_status = updated.setdefault("gate_status", {})
        assert isinstance(gate_status, dict)
        gate_status[gate_id] = "approved"
        fast_path = updated["fast_path"]
        assert isinstance(fast_path, dict)
        gate_inputs = fast_path["gate_inputs"]
        assert isinstance(gate_inputs, dict)
        expected = gate_inputs[gate_id]
        assert isinstance(expected, dict)
        decisions = updated.setdefault("decisions", [])
        assert isinstance(decisions, list)
        decisions.append(
            {
                "gate_id": gate_id,
                "decision": "approved",
                "input_hashes": expected["output_hashes"],
            }
        )
        return updated

    def test_stops_at_gate_resumes_then_returns_all_stage_cache_hit(self) -> None:
        stages = [
            self.stage(stop_gate="gate1"),
            self.stage(
                execution_stage_id="stage-two",
                framework_stage_id="blueprint",
                argv=[
                    sys.executable,
                    str(FIXTURE_STAGE),
                    "--output",
                    "second.json",
                    "--counter",
                    "calls.log",
                ],
                inputs=["first.json"],
                outputs=["second.json"],
                required_gates=["gate1"],
            ),
        ]
        runner = FastPathRunner(self.plan(stages))

        first = runner.run()

        self.assertEqual(first.status, "awaiting_user")
        self.assertTrue((self.task_root / "first.json").is_file())
        self.assertFalse((self.task_root / "second.json").exists())
        store = TaskStorage(self.task_root)
        self.assertEqual(store.read_state()["gate_status"]["gate1"], "awaiting_user")

        store.update_state(lambda state: self.approve_gate(state, "gate1"))
        resumed = runner.run(resume=True)
        cached = runner.run(resume=True)

        self.assertEqual(resumed.status, "succeeded")
        self.assertEqual(cached.status, "cache_hit")
        self.assertEqual(
            (self.task_root / "calls.log").read_text(encoding="utf-8").splitlines(),
            ["called", "called"],
        )
        event_types = [event["event_type"] for event in store.read_events()]
        self.assertIn("command.awaiting_user", event_types)
        self.assertIn("command.cache_hit", event_types)
        self.assertGreaterEqual(len(store.read_metrics()), 5)

    def test_cached_stop_gate_does_not_clear_a_human_block(self) -> None:
        stage = self.stage(stop_gate="gate1")
        first = FastPathRunner(self.plan([stage])).run()
        self.assertEqual(first.status, "awaiting_user")
        store = TaskStorage(self.task_root)
        store.update_state(
            lambda state: state
            | {
                "gate_status": {
                    **state["gate_status"],
                    "gate1": "blocked",
                }
            }
        )

        result = FastPathRunner(self.plan([stage])).run(resume=True)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.error_code, "GATE_BLOCKED")
        self.assertEqual(store.read_state()["gate_status"]["gate1"], "blocked")

    def test_process_start_error_marks_stage_failed(self) -> None:
        stage = self.stage()
        with patch(
            "remix_reference_video.runner._run_stage_command",
            side_effect=OSError("cannot execute stage"),
        ):
            result = FastPathRunner(self.plan([stage])).run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "STAGE_PROCESS_ERROR")
        state = TaskStorage(self.task_root).read_state()
        self.assertEqual(
            state["fast_path"]["stage_status"][stage["execution_stage_id"]]["status"],
            "failed",
        )

    def test_malformed_fast_path_state_returns_stable_validation_failure(self) -> None:
        (self.task_root / "pipeline_state.json").write_text(
            json.dumps(
                {
                    "run_id": "fixture",
                    "execution_mode": "fast-path-v0",
                    "state_revision": 0,
                    "fast_path": [],
                }
            ),
            encoding="utf-8",
        )

        result = FastPathRunner(self.plan([self.stage()])).run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.error_code, "INVALID_PIPELINE_STATE")

    def test_timeout_terminates_the_entire_stage_process_group(self) -> None:
        child_pid_path = self.task_root / "child.pid"
        stage = self.stage(
            argv=[
                sys.executable,
                str(FIXTURE_STAGE),
                "--spawn-child-pid",
                str(child_pid_path),
                "--child-sleep-seconds",
                "5",
                "--child-ignore-term",
                "--sleep-seconds",
                "5",
                "--output",
                "first.json",
            ],
            timeout_seconds=0.2,
        )

        result = FastPathRunner(self.plan([stage])).run()

        self.assertEqual(result.error_code, "STAGE_TIMEOUT")
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 1.0
        while self._process_exists(child_pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        try:
            self.assertFalse(self._process_exists(child_pid))
        finally:
            if self._process_exists(child_pid):
                os.kill(child_pid, signal.SIGKILL)

    @staticmethod
    def _process_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def test_unapproved_prerequisite_gate_prevents_execution(self) -> None:
        runner = FastPathRunner(
            self.plan([self.stage(required_gates=["gate1"])])
        )

        result = runner.run()

        self.assertEqual(result.status, "awaiting_user")
        self.assertEqual(result.error_code, "GATE_NOT_APPROVED")
        self.assertFalse((self.task_root / "calls.log").exists())


    def test_gate_status_without_hash_bound_decision_cannot_resume(self) -> None:
        stages = [
            self.stage(stop_gate="gate1"),
            self.stage(
                execution_stage_id="stage-two",
                framework_stage_id="blueprint",
                argv=[
                    sys.executable,
                    str(FIXTURE_STAGE),
                    "--output",
                    "second.json",
                ],
                inputs=["first.json"],
                outputs=["second.json"],
                required_gates=["gate1"],
            ),
        ]
        runner = FastPathRunner(self.plan(stages))
        self.assertEqual(runner.run().status, "awaiting_user")
        TaskStorage(self.task_root).update_state(
            lambda state: state
            | {
                "gate_status": {**state["gate_status"], "gate1": "approved"},
                "decisions": [{"gate_id": [], "decision": "approved"}],
            }
        )

        result = runner.run(resume=True)

        self.assertEqual(result.status, "awaiting_user")
        self.assertEqual(result.error_code, "GATE_APPROVAL_INVALID")

    def test_non_string_decision_status_is_ignored_without_traceback(self) -> None:
        stages = [
            self.stage(stop_gate="gate1"),
            self.stage(
                execution_stage_id="stage-two",
                framework_stage_id="blueprint",
                argv=[sys.executable, str(FIXTURE_STAGE), "--output", "second.json"],
                inputs=["first.json"],
                outputs=["second.json"],
                required_gates=["gate1"],
            ),
        ]
        runner = FastPathRunner(self.plan(stages))
        self.assertEqual(runner.run().status, "awaiting_user")
        store = TaskStorage(self.task_root)

        def malformed_approval(state: dict[str, object]) -> dict[str, object]:
            updated = self.approve_gate(state, "gate1")
            decisions = updated["decisions"]
            assert isinstance(decisions, list)
            decisions[-1]["status"] = []
            return updated

        store.update_state(malformed_approval)

        result = runner.run(resume=True)

        self.assertEqual(result.status, "awaiting_user")
        self.assertEqual(result.error_code, "GATE_APPROVAL_INVALID")
        self.assertFalse((self.task_root / "second.json").exists())

    def test_tampered_gate_artifact_invalidates_approval(self) -> None:
        first_stage = self.stage(stop_gate="gate1")
        runner = FastPathRunner(self.plan([first_stage]))
        self.assertEqual(runner.run().status, "awaiting_user")
        store = TaskStorage(self.task_root)
        store.update_state(lambda state: self.approve_gate(state, "gate1"))
        (self.task_root / "first.json").write_text("tampered", encoding="utf-8")
        downstream = self.stage(
            execution_stage_id="stage-two",
            framework_stage_id="blueprint",
            argv=[sys.executable, str(FIXTURE_STAGE), "--output", "second.json"],
            inputs=["first.json"],
            outputs=["second.json"],
            required_gates=["gate1"],
        )

        result = FastPathRunner(self.plan([downstream])).run(resume=True)

        self.assertEqual(result.status, "awaiting_user")
        self.assertEqual(result.error_code, "GATE_APPROVAL_INVALID")
        self.assertFalse((self.task_root / "second.json").exists())

    def test_cache_disabled_stage_does_not_clear_a_human_block(self) -> None:
        stage = self.stage(stop_gate="gate1", cache=False)
        runner = FastPathRunner(self.plan([stage]))
        self.assertEqual(runner.run().status, "awaiting_user")
        store = TaskStorage(self.task_root)
        store.update_state(
            lambda state: state
            | {"gate_status": {**state["gate_status"], "gate1": "blocked"}}
        )

        result = runner.run(resume=True)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.error_code, "GATE_BLOCKED")
        self.assertEqual(store.read_state()["gate_status"]["gate1"], "blocked")
        self.assertEqual(
            (self.task_root / "calls.log").read_text(encoding="utf-8").splitlines(),
            ["called"],
        )

    def test_upstream_change_marks_downstream_gate_stale(self) -> None:
        stages = [
            self.stage(stop_gate="gate1"),
            self.stage(
                execution_stage_id="stage-two",
                framework_stage_id="blueprint",
                argv=[sys.executable, str(FIXTURE_STAGE), "--output", "second.json"],
                inputs=["first.json"],
                outputs=["second.json"],
                required_gates=["gate1"],
                stop_gate="gate2",
            ),
        ]
        runner = FastPathRunner(self.plan(stages))
        self.assertEqual(runner.run().status, "awaiting_user")
        store = TaskStorage(self.task_root)
        store.update_state(lambda state: self.approve_gate(state, "gate1"))
        self.assertEqual(runner.run(resume=True).status, "awaiting_user")
        store.update_state(lambda state: self.approve_gate(state, "gate2"))
        (self.task_root / "input.txt").write_text("input-v2", encoding="utf-8")

        changed = runner.run(resume=True)

        self.assertEqual(changed.status, "awaiting_user")
        state = store.read_state()
        self.assertEqual(state["gate_status"]["gate1"], "awaiting_user")
        self.assertEqual(state["gate_status"]["gate2"], "stale")
        retrieval = self.stage(
            execution_stage_id="stage-three",
            framework_stage_id="retrieval",
            argv=[sys.executable, str(FIXTURE_STAGE), "--output", "third.json"],
            inputs=["second.json"],
            outputs=["third.json"],
            required_gates=["gate2"],
        )
        blocked = FastPathRunner(self.plan([retrieval])).run(resume=True)
        self.assertEqual(blocked.status, "awaiting_user")
        self.assertFalse((self.task_root / "third.json").exists())
        self.assertFalse((self.task_root / "second.json").exists())

    def test_duplicate_state_keys_cannot_bypass_manual_contract_protection(self) -> None:
        state_path = self.task_root / "pipeline_state.json"
        state_path.write_text(
            '{"execution_mode":"manual-contract-only",'
            '"execution_mode":"fast-path-v0","state_revision":0}',
            encoding="utf-8",
        )
        before = state_path.read_bytes()

        result = FastPathRunner(self.plan([self.stage()])).run(resume=True)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.error_code, "INVALID_PIPELINE_STATE")
        self.assertEqual(state_path.read_bytes(), before)
        self.assertFalse((self.task_root / "pipeline_events.jsonl").exists())
        self.assertFalse((self.task_root / ".fast_path.lock").exists())

    def test_detects_input_rewritten_with_original_size_and_mtime(self) -> None:
        result = FastPathRunner(
            self.plan(
                [
                    self.stage(
                        argv=[
                            sys.executable,
                            str(FIXTURE_STAGE),
                            "--output",
                            "first.json",
                            "--mutate-preserving-metadata",
                            "input.txt",
                        ]
                    )
                ]
            )
        ).run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "INPUT_MUTATED")

    def test_runner_keeps_business_run_status_outside_fast_path_unchanged(self) -> None:
        stages = [
            self.stage(stop_gate="gate1"),
            self.stage(
                execution_stage_id="stage-two",
                framework_stage_id="blueprint",
                argv=[sys.executable, str(FIXTURE_STAGE), "--output", "second.json"],
                inputs=["first.json"],
                outputs=["second.json"],
                required_gates=["gate1"],
            ),
        ]
        runner = FastPathRunner(self.plan(stages))
        self.assertEqual(runner.run().status, "awaiting_user")
        store = TaskStorage(self.task_root)
        store.update_state(
            lambda state: self.approve_gate(state, "gate1")
            | {"run_status": "business-owned"}
        )

        self.assertEqual(runner.run(resume=True).status, "succeeded")
        state = store.read_state()
        self.assertEqual(state["run_status"], "business-owned")
        self.assertEqual(state["fast_path"]["run_status"], "succeeded")

    def test_concurrent_runs_do_not_execute_the_same_stage_twice(self) -> None:
        stage = self.stage(
            argv=[
                sys.executable,
                str(FIXTURE_STAGE),
                "--output",
                "first.json",
                "--counter",
                "calls.log",
                "--sleep-seconds",
                "0.4",
            ]
        )
        plan = self.plan([stage])
        context = multiprocessing.get_context("fork")
        first_results: multiprocessing.Queue[dict[str, object]] = context.Queue()
        second_results: multiprocessing.Queue[dict[str, object]] = context.Queue()
        first = context.Process(target=_run_plan_in_child, args=(plan, first_results))
        first.start()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state_path = self.task_root / "pipeline_state.json"
            if state_path.exists() and "\"status\": \"running\"" in state_path.read_text():
                break
            time.sleep(0.01)
        else:
            self.fail("first runner did not enter the stage")

        second = context.Process(target=_run_plan_in_child, args=(plan, second_results))
        second.start()
        first.join(timeout=5)
        second.join(timeout=5)
        self.assertEqual(first.exitcode, 0)
        self.assertEqual(second.exitcode, 0)
        results = [first_results.get(timeout=1), second_results.get(timeout=1)]

        self.assertEqual((self.task_root / "calls.log").read_text().splitlines(), ["called"])
        self.assertIn("succeeded", [result["status"] for result in results])
        self.assertIn("TASK_LOCKED", [result["error_code"] for result in results])

    def test_nonzero_command_fails_without_persisting_process_output(self) -> None:
        stage = self.stage(
            argv=[
                sys.executable,
                str(FIXTURE_STAGE),
                "--exit-code",
                "7",
            ]
        )

        result = FastPathRunner(self.plan([stage])).run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "STAGE_COMMAND_FAILED")
        state_text = (self.task_root / "pipeline_state.json").read_text(encoding="utf-8")
        self.assertNotIn("stdout", state_text)
        self.assertNotIn("stderr", state_text)

    def test_timeout_is_measured_and_reported_as_failure(self) -> None:
        stage = self.stage(
            argv=[
                sys.executable,
                str(FIXTURE_STAGE),
                "--sleep-seconds",
                "0.2",
                "--output",
                "first.json",
            ],
            timeout_seconds=0.03,
        )

        result = FastPathRunner(self.plan([stage])).run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "STAGE_TIMEOUT")
        metrics = TaskStorage(self.task_root).read_metrics()
        self.assertGreater(metrics[-1]["elapsed_seconds"], 0)

    def test_missing_declared_output_fails_stage(self) -> None:
        stage = self.stage(
            argv=[sys.executable, str(FIXTURE_STAGE), "--skip-output"]
        )

        result = FastPathRunner(self.plan([stage])).run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "MISSING_OUTPUT")

    def test_preexisting_output_must_be_replaced_by_successful_command(self) -> None:
        (self.task_root / "first.json").write_text("old", encoding="utf-8")
        stage = self.stage(
            argv=[sys.executable, str(FIXTURE_STAGE), "--skip-output"]
        )

        result = FastPathRunner(self.plan([stage])).run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "OUTPUT_NOT_UPDATED")

    def test_input_mutation_and_output_symlink_escape_fail_validation(self) -> None:
        mutating = self.stage(
            argv=[
                sys.executable,
                str(FIXTURE_STAGE),
                "--mutate",
                "input.txt",
                "--output",
                "first.json",
            ]
        )
        mutated = FastPathRunner(self.plan([mutating])).run()
        self.assertEqual(mutated.error_code, "INPUT_MUTATED")

        self.task_root.joinpath("pipeline_state.json").unlink()
        for name in ("pipeline_events.jsonl", "stage_metrics.jsonl", ".fast_path.lock"):
            self.task_root.joinpath(name).unlink(missing_ok=True)
        (self.task_root / "first.json").unlink(missing_ok=True)
        (self.task_root / "input.txt").write_text("restored", encoding="utf-8")
        outside = self.workspace_root / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        escaping = self.stage(
            argv=[
                sys.executable,
                str(FIXTURE_STAGE),
                "--output",
                "first.json",
                "--symlink-target",
                str(outside),
            ]
        )
        escaped = FastPathRunner(self.plan([escaping])).run()
        self.assertEqual(escaped.error_code, "UNSAFE_OUTPUT")

    def test_output_parent_symlink_escape_is_rejected_before_process_start(self) -> None:
        plan = self.plan(
            [
                self.stage(
                    argv=[
                        sys.executable,
                        str(FIXTURE_STAGE),
                        "--output",
                        "late-link/first.json",
                        "--counter",
                        "calls.log",
                    ],
                    outputs=["late-link/first.json"],
                )
            ]
        )
        outside = self.workspace_root / "outside"
        outside.mkdir()
        (self.task_root / "late-link").symlink_to(outside, target_is_directory=True)

        result = FastPathRunner(plan).run()

        self.assertEqual(result.error_code, "UNSAFE_OUTPUT")
        self.assertFalse((outside / "first.json").exists())
        self.assertFalse((self.task_root / "calls.log").exists())

    def test_replaced_task_root_symlink_is_rejected_before_control_writes(self) -> None:
        plan = self.plan([self.stage()])
        original = self.workspace_root / "original-task"
        self.task_root.rename(original)
        outside = self.workspace_root / "outside-task"
        outside.mkdir()
        self.task_root.symlink_to(outside, target_is_directory=True)

        result = FastPathRunner(plan).run()

        self.assertEqual(result.error_code, "UNSAFE_TASK_ROOT")
        for name in (
            "pipeline_state.json",
            "pipeline_events.jsonl",
            "stage_metrics.jsonl",
            ".fast_path.lock",
        ):
            self.assertFalse((outside / name).exists())

    def test_changed_or_corrupt_output_invalidates_cache(self) -> None:
        runner = FastPathRunner(self.plan([self.stage()]))
        self.assertEqual(runner.run().status, "succeeded")
        (self.task_root / "first.json").write_text("tampered", encoding="utf-8")

        result = runner.run(resume=True)

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(
            (self.task_root / "calls.log").read_text(encoding="utf-8").splitlines(),
            ["called", "called"],
        )

    def test_stage_script_change_invalidates_cache(self) -> None:
        tool = self.task_root / "tool.py"
        tool.write_bytes(FIXTURE_STAGE.read_bytes())
        stage = self.stage(
            argv=[
                sys.executable,
                str(tool),
                "--output",
                "first.json",
                "--counter",
                "calls.log",
            ]
        )
        runner = FastPathRunner(self.plan([stage]))
        self.assertEqual(runner.run().status, "succeeded")
        tool.write_text(tool.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        result = runner.run(resume=True)

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(
            (self.task_root / "calls.log").read_text(encoding="utf-8").splitlines(),
            ["called", "called"],
        )

    def test_missing_input_and_missing_executable_fail_before_process_start(self) -> None:
        (self.task_root / "input.txt").unlink()
        missing_input = FastPathRunner(self.plan([self.stage()])).run()
        self.assertEqual(missing_input.error_code, "MISSING_INPUT")

        (self.task_root / "input.txt").write_text("restored", encoding="utf-8")
        missing_executable = FastPathRunner(
            self.plan([self.stage(argv=["definitely-not-an-executable"])])
        ).run()
        self.assertEqual(missing_executable.error_code, "EXECUTABLE_NOT_FOUND")

    def test_manual_contract_pilot_is_rejected_without_any_mutation(self) -> None:
        state_path = self.task_root / "pipeline_state.json"
        state_path.write_text(
            json.dumps(
                {
                    "run_id": "manual-pilot",
                    "execution_mode": "manual-contract-only",
                    "gate_status": {"gate1": "approved"},
                }
            ),
            encoding="utf-8",
        )
        before = {
            path.relative_to(self.task_root): path.read_bytes()
            for path in self.task_root.rglob("*")
            if path.is_file()
        }

        result = FastPathRunner(self.plan([self.stage()])).run()

        after = {
            path.relative_to(self.task_root): path.read_bytes()
            for path in self.task_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.error_code, "MANUAL_CONTRACT_ONLY")
        self.assertEqual(before, after)


class ProductionRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.task = Path(self._temporary.name).resolve() / "task"
        self.task.mkdir()
        self.reference = self.task / "reference.mp4"
        self.reference.write_bytes(b"fixture")

    def test_pending_gate_ignores_aggregate_gate_wait_states(self) -> None:
        runner = ProductionRunner(self.task, ())
        state = {
            "gate_status": {
                "gate3": "awaiting_user",
                "gate4": "awaiting_user",
            }
        }

        self.assertIsNone(runner._pending_gate(state))

    def test_reference_split_stops_at_gate1_and_resume_is_write_free(self) -> None:
        calls: list[str] = []
        task = self.task
        reference = self.reference

        class FixtureAdapter:
            execution_stage_id = "split-reference"
            implementation_version = "fixture-v1"
            stop_gate = "gate1"

            def required_inputs(self) -> tuple[Path, ...]:
                return (reference,)

            def required_gates(self) -> tuple[str, ...]:
                return ()

            def declared_outputs(self) -> tuple[Path, ...]:
                return (task / "recipe.json",)

            def cache_fingerprint(self) -> str:
                return "fixture-fingerprint"

            def execute(self, *, attempt_id: str) -> dict[str, object]:
                calls.append(attempt_id)
                recipe = task / "recipe.json"
                recipe.write_text('{"artifact_type":"recipe"}\n', encoding="utf-8")
                (task / "gate_review_packages").mkdir()
                (task / "gate_review_packages/gate1.json").write_text(
                    json.dumps(
                        {
                            "gate_id": "gate1",
                            "input_hashes": {
                                "recipe.json": hashlib.sha256(recipe.read_bytes()).hexdigest()
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                return {"status": "succeeded", "stop_gate": "gate1"}

        runner = ProductionRunner(self.task, (FixtureAdapter(),))
        runner.initialize(run_id="fixture-run")
        first = runner.run()
        before_resume = {
            path.relative_to(self.task): path.read_bytes()
            for path in self.task.rglob("*")
            if path.is_file()
        }

        resumed = runner.run(resume=True)

        state = TaskStorage(self.task).read_state()
        self.assertEqual(first.status, "awaiting_user")
        self.assertEqual(resumed.status, "awaiting_user")
        self.assertEqual(state["stage_status"]["split-reference"], "succeeded")
        self.assertEqual(state["gate_status"]["gate1"], "awaiting_user")
        self.assertEqual(state["decisions"], [])
        self.assertEqual(len(calls), 1)
        metrics = TaskStorage(self.task).read_metrics()
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0]["execution_stage_id"], "split-reference")
        self.assertEqual(metrics[0]["status"], "succeeded")
        self.assertGreaterEqual(metrics[0]["wall_seconds"], 0)
        self.assertEqual(
            before_resume,
            {
                path.relative_to(self.task): path.read_bytes()
                for path in self.task.rglob("*")
                if path.is_file()
            },
        )

    def test_resume_retries_the_failed_stage(self) -> None:
        attempts = 0
        task = self.task
        reference = self.reference

        class FixtureAdapter:
            execution_stage_id = "split-reference"
            implementation_version = "fixture-v1"

            def required_inputs(self) -> tuple[Path, ...]:
                return (reference,)

            def required_gates(self) -> tuple[str, ...]:
                return ()

            def declared_outputs(self) -> tuple[Path, ...]:
                return (task / "recipe.json",)

            def cache_fingerprint(self) -> str:
                return "fixture-fingerprint"

            def execute(self, *, attempt_id: str) -> dict[str, object]:
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise RuntimeError("transient provider failure")
                (task / "recipe.json").write_text(
                    '{"artifact_type":"recipe"}\n', encoding="utf-8"
                )
                (task / "gate_review_packages").mkdir()
                (task / "gate_review_packages/gate1.json").write_text(
                    json.dumps({"gate_id": "gate1", "input_hashes": {}}),
                    encoding="utf-8",
                )
                return {"status": "succeeded", "stop_gate": "gate1"}

        runner = ProductionRunner(self.task, (FixtureAdapter(),))
        runner.initialize(run_id="fixture-run")

        with self.assertRaisesRegex(RuntimeError, "transient provider failure"):
            runner.run()
        resumed = runner.run(resume=True)

        state = TaskStorage(self.task).read_state()
        self.assertEqual(resumed.status, "awaiting_user")
        self.assertEqual(attempts, 2)
        self.assertEqual(state["stage_status"]["split-reference"], "succeeded")
        self.assertEqual(state["gate_status"]["gate1"], "awaiting_user")
        self.assertEqual(state["blockers"], [])

    def test_gate_review_package_is_sealed_for_approval_service(self) -> None:
        task = self.task
        reference = self.reference

        class FixtureAdapter:
            execution_stage_id = "split-reference"
            implementation_version = "fixture-v1"
            stop_gate = "gate1"

            def required_inputs(self) -> tuple[Path, ...]:
                return (reference,)

            def required_gates(self) -> tuple[str, ...]:
                return ()

            def declared_outputs(self) -> tuple[Path, ...]:
                return (
                    task / "recipe.json",
                    task / "gate_review_packages/gate1.json",
                )

            def cache_fingerprint(self) -> str:
                return "fixture-fingerprint"

            def execute(self, *, attempt_id: str) -> dict[str, object]:
                recipe = task / "recipe.json"
                recipe.write_text('{"artifact_type":"recipe"}\n', encoding="utf-8")
                (task / "gate_review_packages").mkdir()
                (task / "gate_review_packages/gate1.json").write_text(
                    json.dumps(
                        {
                            "gate_id": "gate1",
                            "input_hashes": {
                                "recipe.json": hashlib.sha256(recipe.read_bytes()).hexdigest()
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                return {"status": "succeeded", "stop_gate": "gate1"}

        runner = ProductionRunner(self.task, (FixtureAdapter(),))
        runner.initialize(run_id="fixture-run")
        result = runner.run()
        package = self.task / "gate_review_packages/gate1.json"
        package_value = json.loads(package.read_text(encoding="utf-8"))
        decision = self.task / "gate1-decision.json"
        decision.write_text(
            json.dumps(
                {
                    "decision": "approved",
                    "scope_type": "artifact_set",
                    "scope_ids": ["recipe.json"],
                    "strategy": {},
                }
            ),
            encoding="utf-8",
        )

        approved = ApprovalService(TaskStorage(self.task)).approve(
            gate_id="gate1",
            review_package_hash=hashlib.sha256(package.read_bytes()).hexdigest(),
            decision_file=decision,
            actor="operator-1",
        )

        self.assertEqual(result.status, "awaiting_user")
        self.assertEqual(package_value["run_id"], "fixture-run")
        self.assertEqual(package_value["state_revision"], result.state_revision_after)
        self.assertIn("created_at", package_value)
        self.assertEqual(approved["decision"], "approved")


if __name__ == "__main__":
    unittest.main()
