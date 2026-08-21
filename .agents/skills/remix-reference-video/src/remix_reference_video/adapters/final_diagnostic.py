"""Aggregate shot diagnostics into a business-facing final report."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


class FinalContentDiagnosticAdapter:
    implementation_version = "final-content-diagnostic-adapter-v1"

    def build(self, *, shot_quality: Mapping[str, object], objective: Mapping[str, object]) -> dict[str, object]:
        status = str(shot_quality.get("status", "manual_review"))
        if status not in {"passed", "blocked", "manual_review"}:
            status = "manual_review"
        objectives = objective.get("objectives", []) if isinstance(objective.get("objectives"), list) else []
        objectives = [row for row in objectives if isinstance(row, Mapping) and isinstance(row.get("objective_id"), str)]
        passed_objectives = {
            objective_id
            for shot in shot_quality.get("shots", []) if isinstance(shot, Mapping) and shot.get("status") == "passed"
            for objective_id in shot.get("objective_ids", []) if isinstance(objective_id, str)
        }
        coverage = {str(row["objective_id"]): 1.0 if str(row["objective_id"]) in passed_objectives else 0.0 for row in objectives}
        missing_required = [str(row["objective_id"]) for row in objectives if row.get("required") is True and coverage[str(row["objective_id"])] < 1.0]
        first_three_passed = any(
            isinstance(shot, Mapping) and shot.get("status") in {"passed", "manual_review"} and shot.get("first_three_seconds") is True
            for shot in shot_quality.get("shots", [])
        )
        checks = [
            {"check_id": "shot_quality", "status": status, "score": 1.0 if status == "passed" else None, "evidence_refs": ["shot_quality_report.json"], "earliest_recovery_gate": "gate3_material_selection" if status == "blocked" else None, "business_explanation": "分镜确定性质量检查"},
            {"check_id": "first_three_seconds", "status": "manual_review" if first_three_passed else "blocked", "score": None, "evidence_refs": ["shot_quality_report.json"] if first_three_passed else [], "earliest_recovery_gate": None if first_three_passed else "gate4_pre_generation", "business_explanation": "前三秒需要人工判断是否抓住受众"},
            {"check_id": "consistency", "status": "manual_review" if status != "blocked" else "blocked", "score": None, "evidence_refs": ["shot_quality_report.json"], "earliest_recovery_gate": "gate3_material_selection" if status == "blocked" else None, "business_explanation": "主体与场景连续性"},
            {"check_id": "required_objective_coverage", "status": "blocked" if missing_required else "passed", "score": None if missing_required else 1.0, "evidence_refs": ["shot_quality_report.json", "creative_objective.json"], "earliest_recovery_gate": "gate4_pre_generation" if missing_required else None, "business_explanation": "已批准的必达创作目标"},
        ]
        overall = "blocked" if any(row["status"] == "blocked" for row in checks) else ("manual_review" if any(row["status"] == "manual_review" for row in checks) else "passed")
        body = {"status": overall, "checks": checks, "first_three_seconds": {"status": "manual_review" if first_three_passed else "blocked", "evidence_ref": "shot_quality_report.json" if first_three_passed else None}, "objective_coverage": coverage, "blocked_check_ids": [row["check_id"] for row in checks if row["status"] == "blocked"]}
        raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return {"artifact_type": "final_content_diagnostic_report", "schema_id": "urn:capcut:remix-reference-video:artifact:final-content-diagnostic-report", "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1", "skill_version": "2.0.0-alpha.1", "implementation_version": self.implementation_version, "lifecycle_status": "ready", "input_hashes": {"quality-input.json": hashlib.sha256(raw).hexdigest()}, **body}
