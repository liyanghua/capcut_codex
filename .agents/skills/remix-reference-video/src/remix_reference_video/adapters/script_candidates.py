"""Governed deterministic script candidate generation and validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


class ScriptCandidateGenerator:
    def __init__(self, *, provider: str = "stub", seed: int = 0, model: str = "stub-v1") -> None:
        if provider != "stub":
            raise ValueError("only the deterministic stub provider is enabled in this phase")
        self.provider, self.seed, self.model = provider, seed, model

    def generate(self, inputs: Mapping[str, object]) -> dict[str, object]:
        evidence = inputs.get("evidence", {})
        fragments = evidence.get("fragments", []) if isinstance(evidence, Mapping) else []
        fragments = fragments if isinstance(fragments, list) else []
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
                lines.append({
                    "script_line_id": f"{hypothesis}-{index + 1}",
                    "fragment_id": fragment.get("fragment_id"),
                    "text": text,
                    "narrative_role": fragment.get("narrative_role") or ("opening" if index == 0 else "proof"),
                    "required_actions": fragment.get("required_actions", []),
                    "objective_ids": [],
                    "continuity_before": None if index == 0 else "然后",
                    "continuity_after": "接着" if index < len(fragments) - 1 else None,
                })
            payload = json.dumps(lines, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            candidates.append({
                "script_candidate_id": hashlib.sha256(f"{self.seed}:{hypothesis}:{payload}".encode()).hexdigest()[:16],
                "hypothesis": hypothesis,
                "status": "candidate",
                "lines": lines,
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


class ScriptCandidateValidator:
    def validate(self, artifact: Mapping[str, object], inputs: Mapping[str, object]) -> dict[str, object]:
        rows = artifact.get("candidates", [])
        results = []
        for candidate in rows if isinstance(rows, list) else []:
            if not isinstance(candidate, Mapping):
                continue
            lines = candidate.get("lines", [])
            reasons = []
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
            results.append({"script_candidate_id": candidate.get("script_candidate_id"), "status": "blocked" if reasons else "passed", "reasons": reasons})
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
