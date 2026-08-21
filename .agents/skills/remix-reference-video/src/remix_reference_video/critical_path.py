"""Deterministic critical-path measurement over the production command DAG."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .orchestrator import dag_for_task, default_dag


class CriticalPathError(ValueError):
    pass


class CriticalPathCollector:
    EXCLUDED = frozenset({"init", "archive-approved"})

    def __init__(
        self,
        nodes: Sequence[object] | None = None,
        *,
        task_root: Path | None = None,
    ) -> None:
        if nodes is not None and task_root is not None:
            raise CriticalPathError("provide nodes or task_root, not both")
        self.nodes = tuple(nodes or (dag_for_task(Path(task_root)) if task_root is not None else default_dag()))
        self.by_id = {node.node_id: node for node in self.nodes if node.node_id not in self.EXCLUDED}

    def collect(self, metrics: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        selected: dict[str, Mapping[str, Any]] = {}
        seen_attempts: set[str] = set()
        retry_network = 0.0
        for row in metrics:
            if not isinstance(row, Mapping):
                continue
            attempt = row.get("attempt_id")
            if isinstance(attempt, str):
                if attempt in seen_attempts:
                    raise CriticalPathError(f"duplicate attempt_id: {attempt}")
                seen_attempts.add(attempt)
            if row.get("status") == "failed":
                if row.get("failure_category") == "network_api":
                    retry_network += self._seconds(row.get("wall_seconds"))
                continue
            node_id = row.get("execution_stage_id")
            if node_id not in self.by_id or row.get("status") not in {"succeeded", "cache_hit"}:
                continue
            selected[str(node_id)] = row
        required = set(self.by_id)
        missing = sorted(required - set(selected))
        if missing:
            return {
                "measurement_status": "not_measured",
                "seconds": None,
                "node_durations": {key: self._seconds(value.get("wall_seconds")) for key, value in selected.items()},
                "critical_path_nodes": [],
                "missing_stage_ids": missing,
                "retry_network_seconds": retry_network,
                "retry_network_measurement_status": "measured" if any(row.get("failure_category") == "network_api" for row in metrics if isinstance(row, Mapping)) else "not_measured",
                "evidence_path": "stage_metrics.jsonl",
            }
        critical: dict[str, float] = {}
        path: dict[str, list[str]] = {}
        for node in self.nodes:
            if node.node_id in self.EXCLUDED:
                continue
            duration = self._seconds(selected[node.node_id].get("wall_seconds"))
            predecessors = [dep for dep in node.dependencies if dep not in self.EXCLUDED]
            best = max((critical[dep] for dep in predecessors), default=0.0)
            best_dep = max(predecessors, key=lambda dep: critical[dep], default=None)
            critical[node.node_id] = duration + best
            path[node.node_id] = ([*path[best_dep], node.node_id] if best_dep else [node.node_id])
        terminal = "build-gate5-package"
        return {
            "measurement_status": "measured",
            "seconds": round(critical[terminal], 6),
            "node_durations": {key: self._seconds(value.get("wall_seconds")) for key, value in selected.items()},
            "critical_path_nodes": path[terminal],
            "missing_stage_ids": [],
            "retry_network_seconds": retry_network,
            "retry_network_measurement_status": "measured" if any(row.get("failure_category") == "network_api" for row in metrics if isinstance(row, Mapping)) else "not_measured",
            "evidence_path": "stage_metrics.jsonl",
        }

    @staticmethod
    def _seconds(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise CriticalPathError("wall_seconds must be a non-negative number")
        return float(value)
