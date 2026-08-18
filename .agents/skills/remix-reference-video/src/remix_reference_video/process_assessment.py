"""Pure process and cache assessment collectors for G-B snapshots."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
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
        gate_returns = sum(1 for event in self._dedupe_events(events) if event.get("event_type") in {"gate.returned", "gate.reopened", "rework_completed", "review.rework_completed"})
        valid_decisions = len(approvals)
        approved = sum(1 for row in approvals if row.get("decision") == "approved")
        rejected = sum(1 for row in approvals if row.get("decision") in {"rejected", "changes_requested"})
        metrics_out: dict[str, Any] = {
            "machine_api_critical_path_seconds": self._metric(critical["seconds"], critical["measurement_status"], "stage_metrics.jsonl"),
            "human_wait_seconds": self._metric(timing.get("human_wait_seconds"), timing["human_wait_status"], "pipeline_events.jsonl"),
            "operator_touch_seconds": self._metric(timing.get("operator_touch_seconds"), timing["operator_touch_status"], "pipeline_events.jsonl"),
            "decision_seconds": self._metric(timing.get("decision_seconds"), timing["decision_status"], "pipeline_events.jsonl"),
            "rework_seconds": self._metric(timing.get("rework_seconds"), timing["rework_status"], "pipeline_events.jsonl"),
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
        records = []
        seen: set[str] = set()
        for index, event in enumerate(events):
            event_id = event.get("event_id")
            if isinstance(event_id, str):
                if event_id in seen: continue
                seen.add(event_id)
            occurred = ProcessAssessmentBuilder._event_time(event.get("occurred_at"))
            if occurred is not None: records.append((occurred, index, event))
        records.sort(key=lambda item: (item[0], item[1]))
        ready: dict[str, datetime] = {}
        first_evidence: dict[str, datetime] = {}
        submitted: dict[str, datetime] = {}
        accepted: dict[str, datetime] = {}
        active: dict[tuple[str, str], datetime] = {}
        intervals: list[tuple[str, datetime, datetime]] = []
        changes: dict[str, datetime] = {}
        reworks: list[float] = []
        for occurred, _, event in records:
            kind = event.get("event_type"); gate = str(event.get("gate_id") or "")
            session = str(event.get("session_id") or "")
            payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
            if kind in {"command.awaiting_user", "review_package.ready"} and gate: ready[gate] = occurred
            elif kind == "review.evidence_interaction" and session: first_evidence.setdefault(session, occurred)
            elif kind == "review.decision_submitted" and session: submitted.setdefault(session, occurred)
            elif kind == "review.decision_accepted" and session: accepted.setdefault(session, occurred)
            elif kind == "review.active_start" and session:
                interval = str(payload.get("active_interval_id") or "default")
                active[(session, interval)] = occurred
            elif kind in {"review.active_stop", "review.pause"} and session:
                interval = str(payload.get("active_interval_id") or "default")
                start = active.pop((session, interval), None)
                if start is not None and occurred >= start: intervals.append((session, start, occurred))
            elif kind == "change.applied":
                key = str(event.get("job_id") or event.get("change_request_id") or gate)
                if key: changes[key] = occurred
            elif kind == "review.rework_completed":
                key = str(event.get("job_id") or event.get("change_request_id") or gate)
                start = changes.get(key)
                if start is not None and occurred >= start: reworks.append((occurred - start).total_seconds())
        waits: list[float] = []
        decisions: list[float] = []
        touches: list[float] = []
        session_gates = {str(event.get("session_id")): str(event.get("gate_id")) for _, _, event in records if event.get("session_id") and event.get("gate_id")}
        for session, evidence_at in first_evidence.items():
            gate = session_gates.get(session, "")
            if gate in ready and evidence_at >= ready[gate]: waits.append((evidence_at - ready[gate]).total_seconds())
            if session in accepted and accepted[session] >= evidence_at: decisions.append((accepted[session] - evidence_at).total_seconds())
        for session, start, end in intervals:
            lower = first_evidence.get(session); upper = submitted.get(session)
            if lower is None or upper is None: continue
            clipped_start, clipped_end = max(start, lower), min(end, upper)
            if clipped_end >= clipped_start: touches.append((clipped_end - clipped_start).total_seconds())
        return {
            "operator_touch_seconds": sum(touches) if touches else None, "operator_touch_status": "measured" if touches else "not_measured",
            "human_wait_seconds": sum(waits) if waits else None, "human_wait_status": "measured" if waits else "not_measured",
            "decision_seconds": sum(decisions) if decisions else None, "decision_status": "measured" if decisions else "not_measured",
            "rework_seconds": sum(reworks) if reworks else None, "rework_status": "measured" if reworks else "not_measured",
        }

    @staticmethod
    def _event_time(value: object) -> datetime | None:
        if not isinstance(value, str): return None
        try: return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError: return None

    @staticmethod
    def _dedupe_events(events: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        result: list[Mapping[str, Any]] = []; seen: set[str] = set()
        for event in events:
            event_id = event.get("event_id")
            if isinstance(event_id, str):
                if event_id in seen: continue
                seen.add(event_id)
            result.append(event)
        return result

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
