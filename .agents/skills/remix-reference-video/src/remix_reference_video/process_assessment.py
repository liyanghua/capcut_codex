"""Pure process and cache assessment collectors for G-B snapshots."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .critical_path import CriticalPathCollector


class ProcessAssessmentError(ValueError):
    pass


class ProcessAssessmentBuilder:
    def build(
        self,
        *,
        state: Mapping[str, Any],
        events: Sequence[Mapping[str, Any]],
        metrics: Sequence[Mapping[str, Any]],
        run_id: str,
        execution_mode: str,
        source_paths: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        if state.get("run_id") not in {run_id, None}:
            raise ProcessAssessmentError("state run_id does not match requested run")
        approvals = self._approvals(state.get("decisions"), run_id)
        current: dict[str, Mapping[str, Any]] = {}
        for record in approvals:
            gate = record.get("gate_id")
            if isinstance(gate, str):
                current[gate] = record
        critical = CriticalPathCollector().collect(metrics)
        timing = self._timing(events)
        gate_returns = sum(1 for event in events if event.get("event_type") in {"gate.returned", "gate.reopened", "rework_completed"})
        valid_decisions = len(approvals)
        approved = sum(1 for row in approvals if row.get("decision") == "approved")
        rejected = sum(1 for row in approvals if row.get("decision") in {"rejected", "changes_requested"})
        metrics_out: dict[str, Any] = {
            "machine_api_critical_path_seconds": self._metric(critical["seconds"], critical["measurement_status"], "stage_metrics.jsonl"),
            "human_wait_seconds": self._metric(timing.get("human_wait_seconds"), timing["human_wait_status"], "pipeline_events.jsonl"),
            "operator_touch_seconds": self._metric(timing.get("operator_touch_seconds"), timing["operator_touch_status"], "pipeline_events.jsonl"),
            "rework_seconds": self._not_measured("no explicit rework interval source"),
            "gate_return_count": {"value": gate_returns, "measurement_status": "measured", "evidence_path": "pipeline_events.jsonl"},
            "retry_network_seconds": self._metric(critical["retry_network_seconds"], critical["retry_network_measurement_status"], "stage_metrics.jsonl"),
            "cost": self._not_measured("cost inputs are not present"),
        }
        first_pass_denominator = sum(1 for gate in {row.get("gate_id") for row in approvals} if isinstance(gate, str))
        first_pass_numerator = sum(1 for gate in {row.get("gate_id") for row in approvals} if isinstance(gate, str) and sum(1 for row in approvals if row.get("gate_id") == gate) == 1 and current.get(gate, {}).get("decision") == "approved")
        process_status = "measured" if critical["measurement_status"] == "measured" else "incomplete"
        return {
            "artifact_type": "process_assessment",
            "schema_id": "urn:capcut:remix-reference-video:artifact:process-assessment",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "run_id": run_id,
            "execution_mode": execution_mode,
            "measurement_status": process_status,
            "efficiency_measurement_status": "measured" if timing["operator_touch_status"] == "measured" else "incomplete",
            "approvals": {"records": approvals, "count": valid_decisions, "approved_count": approved, "rejected_count": rejected},
            "current_approvals": current,
            "first_pass_rate": {"value": (first_pass_numerator / first_pass_denominator if first_pass_denominator else None), "measurement_status": "measured" if first_pass_denominator else "not_measured", "sample_size": first_pass_denominator},
            "defect_escape_rate": self._not_measured("defect labels are not present"),
            "gate_return_count": gate_returns,
            "metrics": metrics_out,
            "gate_return_measurement_status": "measured",
            "cache_stage_facts": self._cache_facts(metrics),
            "evidence_paths": list((source_paths or {"state": "pipeline_state.json", "events": "pipeline_events.jsonl", "metrics": "stage_metrics.jsonl"}).values()),
        }

    @staticmethod
    def _approvals(raw: object, run_id: str) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, Mapping) or item.get("decision") not in {"approved", "rejected", "changes_requested"}:
                continue
            record = dict(item)
            record_run = record.get("run_id")
            if record_run is None:
                record["run_id"] = run_id
                record["run_binding"] = "derived_legacy"
            elif record_run != run_id:
                continue
            key = record.get("decision_id")
            if not isinstance(key, str):
                key = f"legacy-{len(result)}"
            if key in seen:
                continue
            seen.add(key)
            result.append(record)
        return result

    @staticmethod
    def _timing(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        active: dict[str, float] = {}
        touch = 0.0
        wait = 0.0
        measured_touch = False
        measured_wait = False
        for event in events:
            kind = event.get("event_type")
            payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else event
            seconds = payload.get("seconds") if isinstance(payload, Mapping) else None
            if kind == "review.active_start" and isinstance(payload, Mapping) and isinstance(payload.get("active_interval_id"), str):
                active[payload["active_interval_id"]] = float(payload.get("at_seconds", 0.0) or 0.0)
            elif kind == "review.active_stop" and isinstance(payload, Mapping) and isinstance(payload.get("active_interval_id"), str) and isinstance(payload.get("at_seconds"), (int, float)):
                start = active.pop(payload["active_interval_id"], None)
                if start is not None:
                    touch += max(0.0, float(payload["at_seconds"]) - start)
                    measured_touch = True
            elif kind == "review.wait_interval" and isinstance(seconds, (int, float)):
                wait += max(0.0, float(seconds)); measured_wait = True
        return {"operator_touch_seconds": touch if measured_touch else None, "operator_touch_status": "measured" if measured_touch else "not_measured", "human_wait_seconds": wait if measured_wait else None, "human_wait_status": "measured" if measured_wait else "not_measured"}

    @staticmethod
    def _metric(value: object, status: str, path: str) -> dict[str, Any]:
        return {"value": value if status == "measured" else None, "measurement_status": status, "evidence_path": path}

    @staticmethod
    def _not_measured(reason: str) -> dict[str, Any]:
        return {"value": None, "measurement_status": "not_measured", "reason": reason}

    @staticmethod
    def _cache_facts(metrics: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"execution_stage_id": None, "cache_source": "none", "hit_count": None, "miss_count": None, "reused_record_count": None, "skipped": None, "evidence_paths": []})
        for row in metrics:
            stage = row.get("execution_stage_id")
            if not isinstance(stage, str):
                continue
            item = grouped[stage]; item["execution_stage_id"] = stage
            if isinstance(row.get("cache_source"), str): item["cache_source"] = row["cache_source"]
            for target, source in (("hit_count", "lookup_hit_count"), ("miss_count", "lookup_miss_count"), ("reused_record_count", "reused_record_count"), ("skipped", "skipped")):
                if source in row: item[target] = row[source]
            if isinstance(row.get("evidence_paths"), list): item["evidence_paths"].extend(row["evidence_paths"])
        return dict(grouped)
