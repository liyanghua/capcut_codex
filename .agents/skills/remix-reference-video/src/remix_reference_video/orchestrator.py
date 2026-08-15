"""Explicit production DAG selection without approval authority."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from .storage import StorageError


class StageAdapter(Protocol):
    execution_stage_id: str
    implementation_version: str

    def required_inputs(self) -> tuple[Path, ...]: ...
    def required_gates(self) -> tuple[str, ...]: ...
    def declared_outputs(self) -> tuple[Path, ...]: ...
    def cache_fingerprint(self) -> str: ...
    def execute(self, *, attempt_id: str) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class DAGNode:
    node_id: str
    dependencies: tuple[str, ...] = ()
    required_gates: tuple[str, ...] = ()
    stop_gate: str | None = None
    parallel_safe: bool = False


@dataclass(frozen=True, slots=True)
class Attempt:
    attempt_id: str
    node_id: str


class ProductionOrchestrator:
    """Select executable nodes from authoritative state; never approves Gates."""

    def __init__(self, nodes: tuple[DAGNode, ...]) -> None:
        if not nodes:
            raise StorageError("production DAG must not be empty")
        self.nodes = nodes
        self._by_id = {node.node_id: node for node in nodes}
        if len(self._by_id) != len(nodes):
            raise StorageError("production DAG node ids must be unique")
        seen: set[str] = set()
        for node in nodes:
            missing = [item for item in node.dependencies if item not in seen]
            if missing:
                raise StorageError(
                    f"DAG dependency must precede {node.node_id}: {', '.join(missing)}"
                )
            seen.add(node.node_id)

    def ready_nodes(self, state: Mapping[str, object]) -> tuple[DAGNode, ...]:
        statuses = self.propagated_statuses(state)
        raw_gates = state.get("gate_status", {})
        gates = raw_gates if isinstance(raw_gates, Mapping) else {}
        ready: list[DAGNode] = []
        for node in self.nodes:
            if statuses.get(node.node_id) in {
                "running",
                "succeeded",
                "blocked",
                "failed",
                "stale",
            }:
                continue
            if any(statuses.get(dependency) != "succeeded" for dependency in node.dependencies):
                continue
            if any(gates.get(gate) != "approved" for gate in node.required_gates):
                continue
            ready.append(node)
        return tuple(ready)

    def propagated_statuses(self, state: Mapping[str, object]) -> dict[str, str]:
        raw = state.get("stage_status", {})
        statuses = dict(raw) if isinstance(raw, Mapping) else {}
        for node in self.nodes:
            if node.node_id in statuses:
                continue
            dependency_states = [statuses.get(item) for item in node.dependencies]
            if "stale" in dependency_states:
                statuses[node.node_id] = "stale"
            elif any(item in {"blocked", "failed"} for item in dependency_states):
                statuses[node.node_id] = "blocked"
        return statuses

    def new_attempt(self, node_id: str) -> Attempt:
        if node_id not in self._by_id:
            raise StorageError(f"unknown production DAG node: {node_id}")
        return Attempt(attempt_id=str(uuid.uuid4()), node_id=node_id)


def default_dag() -> tuple[DAGNode, ...]:
    """Return the normative B0-B5 execution graph from the approved design."""

    return (
        DAGNode("init"),
        DAGNode("split-reference", ("init",), stop_gate="gate1", parallel_safe=True),
        DAGNode("index-assets", ("init",), parallel_safe=True),
        DAGNode("build-coverage-precheck", ("split-reference", "index-assets"), ("gate1",)),
        DAGNode("compile-blueprint", ("build-coverage-precheck",), ("gate1",)),
        DAGNode("compile-mutation-plan", ("compile-blueprint",), ("gate1",)),
        DAGNode("lint-gate2-package", ("compile-mutation-plan",), ("gate1",), "gate2"),
        DAGNode("build-coverage-authoritative", ("lint-gate2-package",), ("gate2",)),
        DAGNode("match-assets", ("build-coverage-authoritative",), ("gate2",)),
        DAGNode("build-material-selection-package", ("match-assets",), ("gate2",), "gate3_material_selection"),
        DAGNode("freeze-fragment-plan", ("build-material-selection-package",), ("gate3_material_selection",)),
        DAGNode("validate-script-evidence", ("freeze-fragment-plan",), ("gate3_material_selection",), "gate3_evidence_closure"),
        DAGNode("summarize-gate3", ("validate-script-evidence",), ("gate3_material_selection", "gate3_evidence_closure")),
        DAGNode("build-production-script", ("summarize-gate3",), ("gate3",), parallel_safe=True),
        DAGNode("materialize-approved-broad", ("summarize-gate3",), ("gate3",), parallel_safe=True),
        DAGNode("build-gate4-pre-package", ("build-production-script", "materialize-approved-broad"), ("gate3",), "gate4_pre_generation"),
        DAGNode("generate-voice", ("build-gate4-pre-package",), ("gate4_pre_generation",)),
        DAGNode("build-reconstruction-timeline", ("generate-voice", "materialize-approved-broad"), ("gate4_pre_generation",)),
        DAGNode("build-gate4-post-package", ("build-reconstruction-timeline",), ("gate4_pre_generation",), "gate4_post_generation"),
        DAGNode("summarize-gate4", ("build-gate4-post-package",), ("gate4_pre_generation", "gate4_post_generation")),
        DAGNode("render-proxy", ("summarize-gate4",), ("gate4",)),
        DAGNode("validate-proxy-boundaries", ("render-proxy",), ("gate4",)),
        DAGNode("render-final", ("validate-proxy-boundaries",), ("gate4",)),
        DAGNode("build-gate5-package", ("render-final",), ("gate4",), "gate5"),
        DAGNode("archive-approved", ("build-gate5-package",), ("gate5",)),
    )
