from __future__ import annotations

import unittest

from remix_reference_video.orchestrator import ProductionOrchestrator, default_dag


class ProductionOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = ProductionOrchestrator(default_dag())

    @staticmethod
    def state(
        *,
        stages: dict[str, str] | None = None,
        gates: dict[str, str] | None = None,
    ) -> dict[str, object]:
        return {
            "stage_status": stages or {},
            "gate_status": gates or {},
            "blockers": [],
        }

    def test_initial_node_and_parallel_reference_index_selection(self) -> None:
        self.assertEqual(
            [node.node_id for node in self.orchestrator.ready_nodes(self.state())],
            ["init"],
        )
        ready = self.orchestrator.ready_nodes(
            self.state(stages={"init": "succeeded"})
        )
        self.assertEqual(
            {node.node_id for node in ready},
            {"split-reference", "index-assets"},
        )
        self.assertTrue(all(node.parallel_safe for node in ready))

    def test_gate_stop_prevents_downstream_selection(self) -> None:
        ready = self.orchestrator.ready_nodes(
            self.state(
                stages={
                    "init": "succeeded",
                    "split-reference": "succeeded",
                    "index-assets": "succeeded",
                },
                gates={"gate1": "awaiting_user"},
            )
        )
        self.assertEqual(ready, ())

    def test_selects_exact_nodes_after_gate1(self) -> None:
        ready = self.orchestrator.ready_nodes(
            self.state(
                stages={
                    "init": "succeeded",
                    "split-reference": "succeeded",
                    "index-assets": "succeeded",
                },
                gates={"gate1": "approved"},
            )
        )
        self.assertEqual(
            [node.node_id for node in ready],
            ["build-coverage-precheck"],
        )

    def test_blocked_or_stale_dependency_blocks_descendants(self) -> None:
        result = self.orchestrator.propagated_statuses(
            self.state(stages={"init": "succeeded", "split-reference": "stale"})
        )
        self.assertEqual(result["build-coverage-precheck"], "stale")
        self.assertEqual(result["compile-blueprint"], "stale")

    def test_attempt_ids_are_unique_and_orchestrator_cannot_approve(self) -> None:
        first = self.orchestrator.new_attempt("split-reference")
        second = self.orchestrator.new_attempt("split-reference")

        self.assertNotEqual(first.attempt_id, second.attempt_id)
        self.assertEqual(first.node_id, "split-reference")
        self.assertFalse(hasattr(self.orchestrator, "approve"))

    def test_voice_preflight_precedes_gate4_package_and_tts(self) -> None:
        node_ids = [node.node_id for node in default_dag()]

        self.assertLess(node_ids.index("voice-preflight"), node_ids.index("build-gate4-pre-package"))
        self.assertLess(node_ids.index("build-gate4-pre-package"), node_ids.index("generate-voice"))
        package = next(node for node in default_dag() if node.node_id == "build-gate4-pre-package")
        self.assertIn("voice-preflight", package.dependencies)


if __name__ == "__main__":
    unittest.main()
