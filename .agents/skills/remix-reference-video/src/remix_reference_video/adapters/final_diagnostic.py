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
        checks = [
            {"check_id": "shot_quality", "status": status, "score": 1.0 if status == "passed" else None, "evidence_refs": ["shot_quality_report.json"], "earliest_recovery_gate": "gate3_material_selection" if status == "blocked" else None, "business_explanation": "分镜确定性质量检查"},
            {"check_id": "first_three_seconds", "status": "manual_review", "score": None, "evidence_refs": [], "earliest_recovery_gate": None, "business_explanation": "前三秒需要人工判断是否抓住受众"},
            {"check_id": "consistency", "status": "manual_review" if status != "blocked" else "blocked", "score": None, "evidence_refs": ["shot_quality_report.json"], "earliest_recovery_gate": "gate3_material_selection" if status == "blocked" else None, "business_explanation": "主体与场景连续性"},
        ]
        objectives = objective.get("objectives", []) if isinstance(objective.get("objectives"), list) else []
        coverage = {str(row.get("objective_id")): 0.0 for row in objectives if isinstance(row, Mapping) and row.get("objective_id")}
        body = {"status": status if status == "blocked" else ("manual_review" if any(row["status"] == "manual_review" for row in checks) else "passed"), "checks": checks, "first_three_seconds": {"status": "manual_review", "evidence_ref": None}, "objective_coverage": coverage, "blocked_check_ids": [row["check_id"] for row in checks if row["status"] == "blocked"]}
        raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return {"artifact_type": "final_content_diagnostic_report", "schema_id": "urn:capcut:remix-reference-video:artifact:final-content-diagnostic-report", "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1", "skill_version": "2.0.0-alpha.1", "implementation_version": self.implementation_version, "lifecycle_status": "ready", "input_hashes": {"quality-input.json": hashlib.sha256(raw).hexdigest()}, **body}
