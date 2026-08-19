"""Deterministic shot-level quality diagnostics for the creative DAG."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


class ShotQualityAdapter:
    implementation_version = "shot-quality-adapter-v1"

    def build(self, *, script: Mapping[str, object], timeline: Mapping[str, object], material: Mapping[str, object], proxy: Mapping[str, object]) -> dict[str, object]:
        lines = {str(row.get("fragment_id")): row for row in script.get("lines", []) if isinstance(row, Mapping)}
        timeline_rows = {str(row.get("fragment_id")): row for row in timeline.get("fragments", []) if isinstance(row, Mapping)}
        material_rows = {str(row.get("fragment_id")): row for row in material.get("fragments", []) if isinstance(row, Mapping)}
        proxy_rows = {str(row.get("shot_id")): row for row in proxy.get("shots", []) if isinstance(row, Mapping)}
        shots = []
        for fragment_id in sorted(set(lines) | set(timeline_rows) | set(material_rows)):
            line = lines.get(fragment_id, {})
            shot = proxy_rows.get(fragment_id, {})
            reasons = []
            required_actions = line.get("required_actions", []) if isinstance(line.get("required_actions"), list) else []
            action_rows = shot.get("action_results", []) if isinstance(shot.get("action_results"), list) else []
            action_by_id = {str(row.get("action_id")): row for row in action_rows if isinstance(row, Mapping)}
            actions = []
            for action_id in required_actions:
                row = action_by_id.get(str(action_id), {})
                status = str(row.get("status", "blocked"))
                if status not in {"passed", "manual_review", "blocked", "not_measured"}:
                    status = "blocked"
                if status == "blocked":
                    reasons.append("required_action_missing")
                actions.append({"action_id": str(action_id), "status": status, "evidence_ref": row.get("evidence_ref")})
            timeline_row = timeline_rows.get(fragment_id, {})
            if not isinstance(timeline_row.get("timeline_start_seconds"), (int, float)) or not isinstance(timeline_row.get("timeline_end_seconds"), (int, float)):
                reasons.append("timeline_missing")
            if fragment_id not in material_rows:
                reasons.append("material_missing")
            continuity = str(shot.get("continuity", "not_measured"))
            if continuity not in {"passed", "blocked", "manual_review", "not_measured"}:
                continuity = "manual_review"
            status = "blocked" if reasons else ("manual_review" if continuity == "manual_review" else "passed")
            recovery = "gate3_material_selection" if any(reason in {"required_action_missing", "material_missing"} for reason in reasons) else ("gate4_pre_generation" if "timeline_missing" in reasons else None)
            shots.append({"shot_id": fragment_id, "status": status, "action_results": actions, "first_three_seconds": False, "script_visual_coherence": "passed" if not reasons else "blocked", "consistency": continuity, "highlight_candidate": bool(shot.get("highlight_candidate", False)), "earliest_recovery_gate": recovery})
        statuses = {str(row["status"]) for row in shots}
        overall = "blocked" if "blocked" in statuses else ("manual_review" if "manual_review" in statuses else "passed")
        return self._envelope({"status": overall, "shots": shots})

    def _envelope(self, body: Mapping[str, object]) -> dict[str, object]:
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return {"artifact_type": "shot_quality_report", "schema_id": "urn:capcut:remix-reference-video:artifact:shot-quality-report", "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1", "skill_version": "2.0.0-alpha.1", "implementation_version": self.implementation_version, "lifecycle_status": "ready", "input_hashes": {"quality-input.json": hashlib.sha256(payload).hexdigest()}, **dict(body)}
