"""Deterministic stage north-star measurements for creative runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .process_assessment import ProcessAssessmentBuilder


class StageNorthStarBuilder:
    """Measure stage outcomes only from authoritative package/artifact sources."""

    def build(
        self,
        *,
        packages: Sequence[Mapping[str, Any]] = (),
        decisions: Sequence[Mapping[str, Any]] = (),
        creative_objective: Mapping[str, Any] | None = None,
        objective_results: Mapping[str, object] | None = None,
        approved_shot_ids: Sequence[str] = (),
        shot_quality_report: Mapping[str, Any] | None = None,
        events: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, dict[str, Any]]:
        package_metrics = self._first_pass(packages, decisions)
        timing = ProcessAssessmentBuilder._timing(events)
        return {
            **package_metrics,
            "weighted_objective_coverage": self._objective_coverage(creative_objective, objective_results),
            "shot_intent_completion": self._shot_completion(approved_shot_ids, shot_quality_report),
            "effective_decision_seconds": self._metric(
                timing.get("decision_seconds"),
                timing.get("decision_status") == "measured",
                "pipeline_events.jsonl",
                "complete evidence_interaction and decision_accepted boundaries are required",
            ),
        }

    def _first_pass(
        self,
        packages: Sequence[Mapping[str, Any]],
        decisions: Sequence[Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        first: dict[str, Mapping[str, Any]] = {}
        decision_index: dict[tuple[str, object], str] = {}
        rework_rounds = 0
        for decision in decisions:
            gate = decision.get("gate_id")
            revision = decision.get("package_revision")
            choice = decision.get("decision")
            if isinstance(gate, str) and choice in {"approved", "changes_requested", "rejected"}:
                decision_index[(gate, revision)] = str(choice)
                if choice in {"changes_requested", "rejected"}:
                    rework_rounds += 1
        for package in packages:
            gate = package.get("gate_id")
            revision = package.get("package_revision")
            if not isinstance(gate, str) or package.get("status") != "awaiting_user" or not isinstance(package.get("input_hash"), str):
                continue
            current = first.get(gate)
            if current is None or self._revision_key(revision) < self._revision_key(current.get("package_revision")):
                first[gate] = package

        def rate(gate: str) -> dict[str, Any]:
            package = first.get(gate)
            if package is None:
                return self._not_measured("no first awaiting_user package bound to an input hash")
            decision = decision_index.get((gate, package.get("package_revision")))
            if decision is None:
                return self._not_measured("first package has no valid decision")
            return {"value": 1.0 if decision == "approved" else 0.0, "measurement_status": "measured", "sample_size": 1, "evidence_path": "pipeline_state.json"}

        return {
            "decomposition_first_pass": rate("gate1"),
            "script_first_pass": rate("gate4_pre_generation"),
            "rework_rounds": {"value": rework_rounds, "measurement_status": "measured", "sample_size": len(decisions), "evidence_path": "pipeline_state.json"},
        }

    def _objective_coverage(
        self,
        objective: Mapping[str, Any] | None,
        results: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        rows = objective.get("objectives") if isinstance(objective, Mapping) else None
        if not isinstance(rows, list) or not rows or not isinstance(results, Mapping):
            return self._not_measured("approved creative objectives or objective results are missing")
        total = 0.0
        passed = 0.0
        for row in rows:
            if not isinstance(row, Mapping) or isinstance(row.get("weight"), bool) or not isinstance(row.get("weight"), (int, float)) or not isinstance(row.get("objective_id"), str):
                return self._not_measured("objective weights are invalid")
            weight = float(row["weight"])
            total += weight
            if results.get(row["objective_id"]) == "passed":
                passed += weight
        if total <= 0:
            return self._not_measured("objective weights have no positive total")
        return {"value": round(passed / total, 6), "measurement_status": "measured", "sample_size": len(rows), "evidence_path": "creative_objective.json"}

    @staticmethod
    def _revision_key(value: object) -> int:
        if isinstance(value, bool):
            return 2**63 - 1
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return 2**63 - 1

    def _shot_completion(
        self,
        approved_shot_ids: Sequence[str],
        report: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        shots = report.get("shots") if isinstance(report, Mapping) else None
        if not approved_shot_ids or not isinstance(shots, list):
            return self._not_measured("approved shots or shot quality report are missing")
        complete: set[str] = set()
        for shot in shots:
            if not isinstance(shot, Mapping) or shot.get("shot_id") not in approved_shot_ids:
                continue
            actions = shot.get("action_results")
            if isinstance(actions, list) and actions and all(
                isinstance(action, Mapping)
                and action.get("status") == "passed"
                and isinstance(action.get("evidence_ref"), str)
                and bool(action.get("evidence_ref"))
                for action in actions
            ):
                complete.add(str(shot["shot_id"]))
        return {"value": len(complete) / len(set(approved_shot_ids)), "measurement_status": "measured", "sample_size": len(set(approved_shot_ids)), "evidence_path": "shot_quality_report.json"}

    @staticmethod
    def _metric(value: object, measured: bool, path: str, reason: str) -> dict[str, Any]:
        if not measured:
            return StageNorthStarBuilder._not_measured(reason)
        return {"value": value, "measurement_status": "measured", "evidence_path": path}

    @staticmethod
    def _not_measured(reason: str) -> dict[str, Any]:
        return {"value": None, "measurement_status": "not_measured", "reason": reason}
