from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.approvals import ApprovalService
from remix_reference_video.orchestrator import default_dag
from remix_reference_video.runner import ProductionRunner
from remix_reference_video.storage import TaskStorage


class _FixtureAdapter:
    def __init__(self, task: Path, node_id: str, stop_gate: str | None) -> None:
        self.task = task
        self.execution_stage_id = node_id
        self.implementation_version = "contract-fixture-v1"
        self.stop_gate = stop_gate
        self.output = task / "fixture-artifacts" / f"{node_id}.json"

    def required_inputs(self) -> tuple[Path, ...]:
        return ()

    def required_gates(self) -> tuple[str, ...]:
        return ()

    def declared_outputs(self) -> tuple[Path, ...]:
        outputs = [self.output]
        if self.execution_stage_id == "build-production-script":
            outputs.append(self.task / "production_script_candidate.json")
        if self.stop_gate:
            outputs.append(self.task / "gate_review_packages" / f"{self.stop_gate}.json")
        return tuple(outputs)

    def cache_fingerprint(self) -> str:
        return f"{self.implementation_version}:{self.execution_stage_id}"

    def execute(self, *, attempt_id: str) -> dict[str, object]:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(
            json.dumps(
                {"stage": self.execution_stage_id, "attempt_id": attempt_id},
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        if self.execution_stage_id == "build-production-script":
            (self.task / "production_script_candidate.json").write_text(
                json.dumps({"script": "fixture"}), encoding="utf-8"
            )
        if self.stop_gate:
            package = self.task / "gate_review_packages" / f"{self.stop_gate}.json"
            package.parent.mkdir(parents=True, exist_ok=True)
            package.write_text(json.dumps({"gate_id": self.stop_gate}), encoding="utf-8")
        return {"status": "succeeded", "stop_gate": self.stop_gate}


class ProductionFixtureTests(unittest.TestCase):
    def test_full_dag_stops_at_each_gate_and_finishes_without_reusing_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            task = Path(temporary).resolve() / "task"
            task.mkdir()
            adapters = tuple(
                _FixtureAdapter(task, node.node_id, node.stop_gate)
                for node in default_dag()
                if node.node_id != "init"
            )
            runner = ProductionRunner(task, adapters)
            runner.initialize(run_id="fixture-full-run")
            service = ApprovalService(TaskStorage(task))
            approved_gates: list[str] = []

            for _ in range(len(adapters) + 10):
                result = runner.run(resume=bool(approved_gates))
                state = TaskStorage(task).read_state()
                pending = next(
                    (
                        gate_id
                        for gate_id, status in state["gate_status"].items()
                        if status == "awaiting_user"
                    ),
                    None,
                )
                if pending is None:
                    if result.status == "succeeded" and all(
                        state["stage_status"].get(adapter.execution_stage_id) == "succeeded"
                        for adapter in adapters
                    ):
                        break
                    continue
                package = task / "gate_review_packages" / f"{pending}.json"
                decision = task / f"decision-{pending}.json"
                decision.write_text(
                    json.dumps(
                        {
                            "decision": "approved",
                            "scope_type": "artifact_set",
                            "scope_ids": [pending],
                            "strategy": {
                                "tts_settings": {"provider": "fixture", "voice": "fixture"}
                            }
                            if pending == "gate4_pre_generation"
                            else {},
                        }
                    ),
                    encoding="utf-8",
                )
                service.approve(
                    gate_id=pending,
                    review_package_hash=hashlib.sha256(package.read_bytes()).hexdigest(),
                    decision_file=decision,
                    actor="fixture-operator",
                )
                approved_gates.append(pending)
            else:
                self.fail("full DAG fixture did not finish")

            final_state = TaskStorage(task).read_state()
            self.assertEqual(approved_gates, [
                "gate1",
                "gate2",
                "gate3_material_selection",
                "gate3_evidence_closure",
                "gate4_pre_generation",
                "gate4_post_generation",
                "gate5",
            ])
            self.assertTrue(all(status == "succeeded" for status in final_state["stage_status"].values()))
            self.assertEqual(final_state["gate_status"]["gate3"], "approved")
            self.assertEqual(final_state["gate_status"]["gate4"], "approved")
            before = {
                path.relative_to(task): path.read_bytes()
                for path in task.rglob("*")
                if path.is_file()
            }
            self.assertEqual(runner.run(resume=True).status, "succeeded")
            self.assertEqual(
                before,
                {
                    path.relative_to(task): path.read_bytes()
                    for path in task.rglob("*")
                    if path.is_file()
                },
            )


if __name__ == "__main__":
    unittest.main()
