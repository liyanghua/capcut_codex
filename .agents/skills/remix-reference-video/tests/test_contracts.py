from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from remix_reference_video import (
    CommandResult,
    ExecutionPlan,
    PipelineState,
    PlanValidationError,
    project_runtime_state,
)


class ExecutionPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.workspace_root = Path(self._temporary_directory.name).resolve()
        self.task_root = self.workspace_root / "work" / "demo"
        self.task_root.mkdir(parents=True)

    @staticmethod
    def stage(**overrides: object) -> dict[str, object]:
        value: dict[str, object] = {
            "execution_stage_id": "probe-reference",
            "framework_stage_id": "performance_proven_video",
            "argv": ["python3", "probe.py", "reference.mp4"],
            "inputs": ["reference.mp4"],
            "outputs": ["recipe.json"],
            "required_gates": [],
            "stop_gate": "gate1",
            "timeout_seconds": 30,
            "cache": True,
        }
        value.update(overrides)
        return value

    @classmethod
    def plan_object(
        cls,
        *,
        task_root: str = "work/demo",
        stages: list[dict[str, object]] | None = None,
        execution_mode: str = "fast-path-v0",
    ) -> dict[str, object]:
        return {
            "task_root": task_root,
            "execution_mode": execution_mode,
            "stages": stages if stages is not None else [cls.stage()],
        }

    def parse_object(self, value: dict[str, object] | None = None) -> ExecutionPlan:
        return ExecutionPlan.from_object(
            value if value is not None else self.plan_object(),
            workspace_root=self.workspace_root,
        )

    def test_parses_object_into_immutable_ordered_dataclasses(self) -> None:
        second_stage = self.stage(
            execution_stage_id="build-blueprint",
            framework_stage_id="blueprint",
            argv=["python3", "blueprint.py"],
            inputs=["recipe.json"],
            outputs=["shot_blueprint.json", "content_baseline.json"],
            required_gates=["gate1"],
            stop_gate="gate2",
            timeout_seconds=45.5,
            cache=False,
        )

        plan = self.parse_object(self.plan_object(stages=[self.stage(), second_stage]))

        self.assertEqual(plan.execution_mode, "fast-path-v0")
        self.assertEqual(plan.task_root, self.task_root)
        self.assertEqual(
            [stage.execution_stage_id for stage in plan.stages],
            ["probe-reference", "build-blueprint"],
        )
        self.assertEqual(plan.stages[0].argv, ("python3", "probe.py", "reference.mp4"))
        self.assertEqual(plan.stages[0].inputs, (self.task_root / "reference.mp4",))
        self.assertEqual(plan.stages[1].required_gates, ("gate1",))
        self.assertFalse(plan.stages[1].cache)

        with self.assertRaises(FrozenInstanceError):
            plan.execution_mode = "other"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            plan.stages[0].argv = ("other",)  # type: ignore[misc]

    def test_parses_json_without_key_order_or_whitespace_affecting_fingerprint(self) -> None:
        (self.task_root / "reference.mp4").write_bytes(b"reference-content")
        value = self.plan_object()
        reordered_stage = dict(reversed(list(self.stage().items())))
        reordered_value = {
            "stages": [reordered_stage],
            "execution_mode": "fast-path-v0",
            "task_root": "work/demo",
        }

        compact = ExecutionPlan.from_json(
            json.dumps(value, separators=(",", ":")),
            workspace_root=self.workspace_root,
        )
        pretty_reordered = ExecutionPlan.from_json(
            json.dumps(reordered_value, indent=4),
            workspace_root=self.workspace_root,
        )

        self.assertEqual(compact, pretty_reordered)
        self.assertEqual(
            compact.input_fingerprint("probe-reference"),
            pretty_reordered.input_fingerprint("probe-reference"),
        )

    def test_rejects_malformed_json_with_a_contract_error(self) -> None:
        for malformed in ("{", b"\xff"):
            with self.subTest(malformed=malformed):
                with self.assertRaisesRegex(PlanValidationError, "plan JSON is invalid"):
                    ExecutionPlan.from_json(
                        malformed,
                        workspace_root=self.workspace_root,
                    )

    def test_rejects_duplicate_json_keys_at_plan_or_stage_level(self) -> None:
        valid_json = json.dumps(self.plan_object(), separators=(",", ":"))
        duplicate_values = [
            valid_json.replace(
                '"task_root":"work/demo"',
                '"task_root":"work/demo","task_root":"work/other"',
                1,
            ),
            valid_json.replace(
                '"argv":["python3","probe.py","reference.mp4"]',
                '"argv":["python3"],"argv":["other"]',
                1,
            ),
        ]

        for value in duplicate_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(PlanValidationError, "duplicate JSON key"):
                    ExecutionPlan.from_json(
                        value,
                        workspace_root=self.workspace_root,
                    )

    def test_rejects_non_string_object_keys_with_a_contract_error(self) -> None:
        value = self.plan_object()
        value[1] = "unexpected"  # type: ignore[index]

        with self.assertRaisesRegex(PlanValidationError, "keys must be strings"):
            self.parse_object(value)

    def test_fingerprint_tracks_plan_semantics_and_input_content_not_output_content(self) -> None:
        input_path = self.task_root / "reference.mp4"
        output_path = self.task_root / "recipe.json"
        input_path.write_bytes(b"version-one")
        plan = self.parse_object()

        initial = plan.input_fingerprint("probe-reference")
        self.assertEqual(initial, plan.input_fingerprint("probe-reference"))

        output_path.write_bytes(b"generated-output")
        self.assertEqual(initial, plan.input_fingerprint("probe-reference"))

        input_path.write_bytes(b"version-two")
        self.assertNotEqual(initial, plan.input_fingerprint("probe-reference"))

        changed_argv = self.parse_object(
            self.plan_object(stages=[self.stage(argv=["python3", "probe.py", "--strict"])])
        )
        self.assertNotEqual(
            plan.input_fingerprint("probe-reference"),
            changed_argv.input_fingerprint("probe-reference"),
        )

    def test_fingerprint_distinguishes_missing_input_from_empty_file(self) -> None:
        input_path = self.task_root / "reference.mp4"
        plan = self.parse_object()

        missing = plan.input_fingerprint("probe-reference")
        input_path.write_bytes(b"")
        present_but_empty = plan.input_fingerprint("probe-reference")

        self.assertNotEqual(missing, present_but_empty)

    def test_rejects_a_shell_command_string_instead_of_an_argv_array(self) -> None:
        value = self.plan_object(stages=[self.stage(argv="python3 probe.py")])

        with self.assertRaisesRegex(PlanValidationError, "argv.*array"):
            self.parse_object(value)

    def test_rejects_empty_or_non_string_argv_values(self) -> None:
        invalid_values: list[object] = [[], [""], ["python3", 7]]

        for argv in invalid_values:
            with self.subTest(argv=argv):
                value = self.plan_object(stages=[self.stage(argv=argv)])
                with self.assertRaises(PlanValidationError):
                    self.parse_object(value)

    def test_rejects_task_and_stage_paths_that_escape_declared_roots(self) -> None:
        outside = self.workspace_root.parent / "outside-input.mp4"
        invalid_values = [
            self.plan_object(task_root="../outside-task"),
            self.plan_object(stages=[self.stage(inputs=["../../../outside-input.mp4"])]),
            self.plan_object(stages=[self.stage(outputs=[str(outside)])]),
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(PlanValidationError, "path|root"):
                    self.parse_object(value)

    def test_rejects_symlink_paths_that_resolve_outside_task_root(self) -> None:
        outside_directory = self.workspace_root / "outside"
        outside_directory.mkdir()
        (self.task_root / "escape").symlink_to(outside_directory, target_is_directory=True)
        value = self.plan_object(stages=[self.stage(inputs=["escape/input.mp4"])])

        with self.assertRaisesRegex(PlanValidationError, "task root"):
            self.parse_object(value)

    def test_rejects_unsupported_execution_modes(self) -> None:
        for mode in ("experimental-fast-path-v0", "manual-contract-only", "full", ""):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(PlanValidationError, "execution_mode"):
                    self.parse_object(self.plan_object(execution_mode=mode))

    def test_rejects_unknown_framework_stage_and_duplicate_execution_stage_ids(self) -> None:
        with self.assertRaisesRegex(PlanValidationError, "framework_stage_id"):
            self.parse_object(
                self.plan_object(stages=[self.stage(framework_stage_id="sixth-stage")])
            )

        duplicate = self.stage(framework_stage_id="blueprint")
        with self.assertRaisesRegex(PlanValidationError, "execution_stage_id.*unique"):
            self.parse_object(self.plan_object(stages=[self.stage(), duplicate]))

    def test_rejects_invalid_gate_timeout_and_cache_shapes(self) -> None:
        invalid_stages = [
            self.stage(required_gates="gate1"),
            self.stage(required_gates=[""]),
            self.stage(stop_gate=""),
            self.stage(timeout_seconds=0),
            self.stage(timeout_seconds=True),
            self.stage(timeout_seconds=float("nan")),
            self.stage(timeout_seconds=float("inf")),
            self.stage(timeout_seconds=10**1000),
            self.stage(timeout_seconds=1e300),
            self.stage(cache="yes"),
        ]

        for stage in invalid_stages:
            with self.subTest(stage=stage):
                with self.assertRaises(PlanValidationError):
                    self.parse_object(self.plan_object(stages=[stage]))

    def test_rejects_reserved_task_state_paths_as_outputs(self) -> None:
        for reserved_path in (
            "pipeline_state.json",
            "pipeline_events.jsonl",
            "stage_metrics.jsonl",
            ".fast_path.lock",
        ):
            with self.subTest(reserved_path=reserved_path):
                with self.assertRaisesRegex(PlanValidationError, "reserved"):
                    self.parse_object(
                        self.plan_object(stages=[self.stage(outputs=[reserved_path])])
                    )

    def test_rejects_noncanonical_or_skippable_gate_sequences(self) -> None:
        blueprint_without_gate1 = self.stage(
            execution_stage_id="build-blueprint",
            framework_stage_id="blueprint",
            argv=["python3", "blueprint.py"],
            inputs=["recipe.json"],
            outputs=["shot_blueprint.json"],
            required_gates=[],
            stop_gate=None,
        )
        reconstruction = self.stage(
            execution_stage_id="render",
            framework_stage_id="reconstruction",
            argv=["python3", "render.py"],
            inputs=["recipe.json"],
            outputs=["remix.mp4"],
            required_gates=["gate1"],
            stop_gate=None,
        )
        gate_leap = self.stage(
            execution_stage_id="leap-to-gate5",
            framework_stage_id="blueprint",
            argv=["python3", "blueprint.py"],
            inputs=["recipe.json"],
            outputs=["shot_blueprint.json"],
            required_gates=["gate1"],
            stop_gate="gate5",
        )
        first_gate_leap = self.stage(stop_gate="gate5")
        invalid_plans = [
            self.plan_object(stages=[self.stage(required_gates=["unknown-gate"])]),
            self.plan_object(stages=[self.stage(stop_gate="unknown-gate")]),
            self.plan_object(stages=[self.stage(), blueprint_without_gate1]),
            self.plan_object(stages=[self.stage(), reconstruction]),
            self.plan_object(stages=[self.stage(), gate_leap]),
            self.plan_object(stages=[first_gate_leap]),
        ]

        for value in invalid_plans:
            with self.subTest(value=value):
                with self.assertRaisesRegex(PlanValidationError, "gate"):
                    self.parse_object(value)


class PipelineStateTests(unittest.TestCase):
    @staticmethod
    def valid_state(**overrides: object) -> dict[str, object]:
        state: dict[str, object] = {
            "execution_mode": "track-b-production",
            "run_id": "run-1",
            "state_revision": 3,
            "active_stage": "retrieval",
            "active_command": "match-assets",
            "stage_status": {
                "performance_proven_video": "succeeded",
                "retrieval": "running",
            },
            "gate_status": {
                "gate1": "approved",
                "gate2": "approved",
                "gate3_material_selection": "awaiting_user",
                "gate3_evidence_closure": "not_ready",
                "gate3": "awaiting_user",
            },
            "decisions": [],
            "artifacts": {},
            "blockers": [],
            "cache_summary": {},
        }
        state.update(overrides)
        return state

    def test_parses_authoritative_track_b_state(self) -> None:
        state = PipelineState.from_object(self.valid_state())

        self.assertEqual(state.execution_mode, "track-b-production")
        self.assertEqual(state.state_revision, 3)
        self.assertEqual(state.gate_status["gate3_material_selection"], "awaiting_user")

    def test_rejects_invalid_identity_revision_work_and_gate_status(self) -> None:
        invalid = [
            {"execution_mode": "manual-contract-only"},
            {"run_id": ""},
            {"state_revision": -1},
            {"stage_status": {"retrieval": "approved"}},
            {"gate_status": {"gate3_material_selection": "running"}},
            {"gate_status": {"unknown": "approved"}},
        ]
        for override in invalid:
            with self.subTest(override=override), self.assertRaises(PlanValidationError):
                PipelineState.from_object(self.valid_state(**override))

    def test_legacy_projection_never_invents_production_mode(self) -> None:
        projection = project_runtime_state(
            {"run_id": "legacy", "gate_status": {"gate1": "approved"}}
        )

        self.assertFalse(projection["supported"])
        self.assertIsNone(projection["execution_mode"])
        self.assertIsNone(projection["active_stage"])
        self.assertIsNone(projection["state_revision"])


class CommandResultTests(unittest.TestCase):
    def test_exposes_runner_result_fields_as_an_immutable_value(self) -> None:
        result = CommandResult(
            status="awaiting_user",
            exit_code=0,
            request_id="request-1",
            invocation_id="invocation-1",
            idempotency_key="idem-1",
            state_revision_before=4,
            state_revision_after=5,
            event_sequence=12,
            next_actions=("approve:gate1",),
            error_code=None,
        )

        self.assertEqual(result.status, "awaiting_user")
        self.assertEqual(result.next_actions, ("approve:gate1",))
        with self.assertRaises(FrozenInstanceError):
            result.status = "succeeded"  # type: ignore[misc]

    def test_rejects_invalid_result_identity_and_revision_values(self) -> None:
        base = {
            "status": "failed",
            "exit_code": 1,
            "request_id": "request-1",
            "invocation_id": "invocation-1",
            "idempotency_key": "idem-1",
            "state_revision_before": 4,
            "state_revision_after": 4,
            "event_sequence": 12,
            "next_actions": (),
            "error_code": "STAGE_FAILED",
        }
        invalid_overrides = [
            {"status": ""},
            {"request_id": ""},
            {"state_revision_before": -1},
            {"state_revision_after": 3},
            {"event_sequence": -1},
            {"next_actions": ["retry"]},
        ]

        for override in invalid_overrides:
            with self.subTest(override=override):
                with self.assertRaises(PlanValidationError):
                    CommandResult(**(base | override))


if __name__ == "__main__":
    unittest.main()
