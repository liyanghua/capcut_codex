"""Governed deterministic script candidate generation and validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


class ScriptCandidateGenerator:
    def __init__(self, *, provider: str | None = None, seed: int = 0, model: str = "stub-v1") -> None:
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("script candidate provider configuration is required")
        if provider != "stub":
            raise ValueError("only the deterministic stub provider is enabled in this phase")
        self.provider, self.seed, self.model = provider, seed, model

    def generate(self, inputs: Mapping[str, object]) -> dict[str, object]:
        evidence = inputs.get("evidence", {})
        fragments = evidence.get("fragments", []) if isinstance(evidence, Mapping) else []
        fragments = fragments if isinstance(fragments, list) else []
        objective = inputs.get("objective", {})
        objective_rows = objective.get("objectives", []) if isinstance(objective, Mapping) else []
        objective_rows = [row for row in objective_rows if isinstance(row, Mapping)]
        hypotheses = ("problem_solution", "proof_demo", "scene_benefit")
        candidates = []
        for hypothesis in hypotheses:
            lines = []
            for index, fragment in enumerate(fragments):
                if not isinstance(fragment, Mapping):
                    continue
                text = str(fragment.get("voice_text", "")).strip()
                if not text:
                    continue
                claim_ids = self._strings(fragment.get("claim_ids"))
                required_actions = self._strings(fragment.get("required_actions"))
                role = str(fragment.get("narrative_role") or ("opening" if index == 0 else "proof"))
                lines.append({
                    "script_line_id": f"{hypothesis}-{index + 1}",
                    "fragment_id": fragment.get("fragment_id"),
                    "text": text,
                    "objective_id": self._objective_id(index, role, claim_ids, required_actions, objective_rows),
                    "narrative_role": role,
                    "required_actions": required_actions,
                    "claim_ids": claim_ids,
                    "evidence_row_ref": fragment.get("evidence_row_ref") or f"evidence:{fragment.get('fragment_id')}",
                    "visual_intent": dict(fragment.get("visual_intent", {})) if isinstance(fragment.get("visual_intent"), Mapping) else {"required_actions": required_actions},
                    "visual_duration_budget_seconds": fragment.get("visual_duration_budget_seconds"),
                    "estimated_duration_seconds": self._estimate_seconds(text),
                    "continuity_before": None if index == 0 else "然后",
                    "continuity_after": "接着" if index < len(fragments) - 1 else None,
                })
            payload = json.dumps(lines, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            candidates.append({
                "script_candidate_id": hashlib.sha256(f"{self.seed}:{hypothesis}:{payload}".encode()).hexdigest()[:16],
                "creative_hypothesis": hypothesis,
                "status": "candidate",
                "lines": lines,
                "objective_coverage": sorted(self._covered_objectives(lines)),
                "uncovered_objectives": sorted(
                    str(row.get("objective_id")) for row in objective_rows
                    if isinstance(row.get("objective_id"), str)
                    and str(row["objective_id"]) not in self._covered_objectives(lines)
                ),
                "risk_notes": [],
                "provider": self.provider,
                "model": self.model,
                "prompt_template_version": "script_candidate_prompt_v1",
                "seed": self.seed,
                "input_hashes": {"inputs": hashlib.sha256(json.dumps(inputs, ensure_ascii=False, sort_keys=True).encode()).hexdigest()},
            })
        input_hash = hashlib.sha256(
            json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "artifact_type": "script_candidates",
            "schema_id": "urn:capcut:remix-reference-video:artifact:script-candidates",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "implementation_version": "script-candidate-generator-v1",
            "lifecycle_status": "ready",
            "input_hashes": {"creative-inputs.json": input_hash},
            "candidates": candidates,
            "provider": self.provider,
            "model": self.model,
            "prompt_template_version": "script_candidate_prompt_v1",
            "seed": self.seed,
        }

    @staticmethod
    def _strings(value: object) -> list[str]:
        return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []

    @staticmethod
    def _estimate_seconds(text: str) -> float:
        content = sum(1 for char in text if not char.isspace() and char not in "，,、；;：:。.!！?？")
        pauses = sum(0.25 for char in text if char in "，,、；;：:。.!！?？")
        return round(content / 4.6 + pauses, 3)

    @staticmethod
    def _objective_id(
        index: int,
        role: str,
        claim_ids: list[str],
        required_actions: list[str],
        objectives: list[Mapping[str, object]],
    ) -> str | None:
        known = {str(row.get("objective_id")) for row in objectives if isinstance(row.get("objective_id"), str)}
        if index == 0 and "opening_hook" in known:
            return "opening_hook"
        if "show_product" in required_actions and "product_appearance" in known:
            return "product_appearance"
        for claim_id in claim_ids:
            objective_id = f"claim:{claim_id}"
            if objective_id in known:
                return objective_id
        if role in {"close", "收束"} and "close" in known:
            return "close"
        return None

    @staticmethod
    def _covered_objectives(lines: list[Mapping[str, object]]) -> set[str]:
        covered: set[str] = set()
        for line in lines:
            objective_id = line.get("objective_id")
            if isinstance(objective_id, str) and objective_id:
                covered.add(objective_id)
            for claim_id in line.get("claim_ids", []):
                if isinstance(claim_id, str) and claim_id:
                    covered.add(f"claim:{claim_id}")
        return covered


class ScriptCandidateValidator:
    def validate(self, artifact: Mapping[str, object], inputs: Mapping[str, object]) -> dict[str, object]:
        rows = artifact.get("candidates", [])
        objective = inputs.get("objective", {}) if isinstance(inputs, Mapping) else {}
        objective_rows = objective.get("objectives", []) if isinstance(objective, Mapping) else []
        objective_rows = [row for row in objective_rows if isinstance(row, Mapping)]
        required_objectives = {
            str(row["objective_id"]) for row in objective_rows
            if row.get("required") is True and isinstance(row.get("objective_id"), str)
        }
        forbidden = self._strings(objective.get("forbidden_claims")) if isinstance(objective, Mapping) else []
        results = []
        for candidate in rows if isinstance(rows, list) else []:
            if not isinstance(candidate, Mapping):
                continue
            lines = candidate.get("lines", [])
            reasons: list[str] = []
            checks: dict[str, str] = {}
            if not isinstance(lines, list) or not lines:
                reasons.append("missing_lines")
            else:
                roles = [str(line.get("narrative_role")) for line in lines if isinstance(line, Mapping)]
                if roles and roles[0] not in {"opening", "context", "problem"}:
                    reasons.append("missing_opening_role")
                if any(not isinstance(line, Mapping) or not str(line.get("text", "")).strip() for line in lines):
                    reasons.append("empty_script_line")
                if any(roles[index] == roles[index + 1] == "proof" for index in range(len(roles) - 1)):
                    reasons.append("consecutive_pure_proof")
                if any(not isinstance(line.get("evidence_row_ref"), str) or not line["evidence_row_ref"] for line in lines if isinstance(line, Mapping)):
                    reasons.append("missing_evidence_reference")
                if any(not isinstance(line.get("visual_intent"), Mapping) for line in lines if isinstance(line, Mapping)):
                    reasons.append("missing_visual_intent")
                if any(not isinstance(line.get("estimated_duration_seconds"), (int, float)) for line in lines if isinstance(line, Mapping)):
                    reasons.append("missing_duration_estimate")
                for line in lines:
                    if not isinstance(line, Mapping):
                        continue
                    budget = line.get("visual_duration_budget_seconds")
                    estimate = line.get("estimated_duration_seconds")
                    if isinstance(budget, (int, float)) and not isinstance(budget, bool) and isinstance(estimate, (int, float)) and not isinstance(estimate, bool) and float(estimate) > float(budget):
                        reasons.append("visual_budget_exceeded")
            covered = ScriptCandidateGenerator._covered_objectives([line for line in lines if isinstance(line, Mapping)]) if isinstance(lines, list) else set()
            missing_required = required_objectives - covered
            if missing_required:
                reasons.append("required_objective_uncovered")
            text = "".join(str(line.get("text", "")) for line in lines if isinstance(line, Mapping)) if isinstance(lines, list) else ""
            if any(claim and claim in text for claim in forbidden):
                reasons.append("forbidden_claim")
            checks["required_objectives"] = "passed" if not missing_required else "blocked"
            checks["evidence_closure"] = "passed" if "missing_evidence_reference" not in reasons else "blocked"
            checks["visual_budget"] = "blocked" if "visual_budget_exceeded" in reasons else "passed"
            margin = sum(
                float(line["visual_duration_budget_seconds"]) - float(line["estimated_duration_seconds"])
                for line in lines if isinstance(line, Mapping)
                and isinstance(line.get("visual_duration_budget_seconds"), (int, float))
                and not isinstance(line.get("visual_duration_budget_seconds"), bool)
                and isinstance(line.get("estimated_duration_seconds"), (int, float))
                and not isinstance(line.get("estimated_duration_seconds"), bool)
            )
            weighted = sum(float(row.get("weight", 0.0)) for row in objective_rows if row.get("objective_id") in covered and isinstance(row.get("weight"), (int, float)) and not isinstance(row.get("weight"), bool))
            results.append({"script_candidate_id": candidate.get("script_candidate_id"), "status": "blocked" if reasons else "passed", "reason_codes": sorted(set(reasons)), "objective_coverage": sorted(covered), "weighted_objective_coverage": round(weighted, 6), "budget_margin_seconds": round(margin, 3), "checks": checks})
        status = "blocked" if results and all(row["status"] == "blocked" for row in results) else "passed"
        input_hash = hashlib.sha256(
            json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "artifact_type": "script_candidate_validation_report",
            "schema_id": "urn:capcut:remix-reference-video:artifact:script-candidate-validation-report",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "implementation_version": "script-candidate-validator-v1",
            "lifecycle_status": "ready",
            "input_hashes": {"script_candidates.json": input_hash},
            "status": status,
            "candidates": results,
            "validation_policy_version": "script_candidate_rank_v1",
        }

    def select(self, artifact: Mapping[str, object], validation: Mapping[str, object]) -> Mapping[str, object]:
        candidates = {
            str(row.get("script_candidate_id")): row
            for row in artifact.get("candidates", []) if isinstance(row, Mapping) and isinstance(row.get("script_candidate_id"), str)
        }
        passed = [row for row in validation.get("candidates", []) if isinstance(row, Mapping) and row.get("status") == "passed" and str(row.get("script_candidate_id")) in candidates]
        if not passed:
            raise ValueError("no passed script candidate")
        ranked = sorted(
            passed,
            key=lambda row: (
                -len(row.get("objective_coverage", [])) if isinstance(row.get("objective_coverage"), list) else 0,
                -float(row.get("weighted_objective_coverage", 0.0)),
                -float(row.get("budget_margin_seconds", 0.0)),
                str(row.get("script_candidate_id")),
            ),
        )
        return candidates[str(ranked[0]["script_candidate_id"])]

    @staticmethod
    def _strings(value: object) -> list[str]:
        return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []
