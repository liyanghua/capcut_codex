"""Compile a candidate script from Gate 2 boundaries and approved evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..storage import read_json_object


class ScriptCompileError(ValueError):
    """Raised when evidence cannot support a production script candidate."""


class ProductionScriptCompiler:
    implementation_version = "production-script-compiler-v2"

    def compile(
        self,
        *,
        content_baseline_path: Path,
        mutation_plan_path: Path,
        evidence_matrix_path: Path,
        evidence_approval_record: Mapping[str, object],
        narrative_report_path: Path | None = None,
    ) -> dict[str, Any]:
        paths = {
            "content_baseline.json": self._canonical_path(
                content_baseline_path, "content_baseline.json"
            ),
            "mutation_plan.json": self._canonical_path(
                mutation_plan_path, "mutation_plan.json"
            ),
            "script_evidence_matrix.json": self._canonical_path(
                evidence_matrix_path, "script_evidence_matrix.json"
            ),
        }
        baseline = read_json_object(paths["content_baseline.json"])
        mutation = read_json_object(paths["mutation_plan.json"])
        evidence = read_json_object(paths["script_evidence_matrix.json"])
        narrative_contract = baseline.get("narrative_contract_version")
        if narrative_contract == "narrative_contract_v1":
            if narrative_report_path is None:
                raise ScriptCompileError("narrative_coherence_report is required for narrative_contract_v1")
            paths["narrative_coherence_report.json"] = self._canonical_path(
                narrative_report_path, "narrative_coherence_report.json"
            )
            narrative = read_json_object(paths["narrative_coherence_report.json"])
            if narrative.get("artifact_type") != "narrative_coherence_report":
                raise ScriptCompileError("narrative_coherence_report artifact is required")
            if narrative.get("status") != "passed":
                raise ScriptCompileError(
                    f"narrative coherence gate is {narrative.get('status')!r}; script compilation requires a passed report"
                )
            narrative_rows = {
                str(row.get("fragment_id")): row
                for row in narrative.get("fragments", [])
                if isinstance(row, Mapping) and isinstance(row.get("fragment_id"), str)
            }
        else:
            narrative_rows = {}
        if baseline.get("artifact_type") != "content_baseline":
            raise ScriptCompileError("content_baseline artifact is required")
        if mutation.get("artifact_type") != "mutation_plan":
            raise ScriptCompileError("mutation_plan artifact is required")
        if evidence.get("artifact_type") != "script_evidence_matrix":
            raise ScriptCompileError("script_evidence_matrix artifact is required")
        evidence_hash = self._sha256(paths["script_evidence_matrix.json"])
        approval_hashes = evidence_approval_record.get("input_hashes")
        if (
            evidence_approval_record.get("gate_id") != "gate3_evidence_closure"
            or evidence_approval_record.get("decision") != "approved"
            or not isinstance(approval_hashes, Mapping)
            or approval_hashes.get("script_evidence_matrix.json") != evidence_hash
        ):
            raise ScriptCompileError(
                "script_evidence_matrix must be approved for its current hash"
            )

        claims = self._claim_ids(baseline.get("claims"))
        forbidden = self._string_list(baseline.get("forbidden_claims", []), "forbidden_claims")
        fragments = self._fragments(baseline.get("fragments"))
        fallbacks = self._fallbacks(mutation.get("allowed_fallbacks", []))
        rows = evidence.get("rows")
        if not isinstance(rows, list):
            raise ScriptCompileError("evidence rows must be an array")
        by_fragment: dict[str, Mapping[str, object]] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise ScriptCompileError("evidence row must be an object")
            fragment_id = row.get("fragment_id")
            if not isinstance(fragment_id, str) or fragment_id not in fragments:
                raise ScriptCompileError("evidence row references unknown fragment")
            if fragment_id in by_fragment:
                raise ScriptCompileError(f"duplicate evidence row: {fragment_id}")
            by_fragment[fragment_id] = row

        required = {
            fragment_id
            for fragment_id, fragment in fragments.items()
            if isinstance(fragment.get("narration"), str) and fragment["narration"].strip()
        }
        missing = sorted(
            fragment_id
            for fragment_id in required
            if fragment_id not in by_fragment
            or not str(by_fragment[fragment_id].get("closure_decision", "")).startswith("closed")
        )
        if missing:
            raise ScriptCompileError(f"missing closed evidence: {', '.join(missing)}")

        lines: list[dict[str, object]] = []
        for fragment_id, row in by_fragment.items():
            closure = row.get("closure_decision")
            if not isinstance(closure, str) or not closure.startswith("closed"):
                continue
            row_claims = self._string_list(
                row.get("approved_claim_ids", []), f"{fragment_id}.approved_claim_ids"
            )
            if not set(row_claims) <= claims:
                raise ScriptCompileError(f"{fragment_id} exceeds Gate 2 claim boundary")
            fallback_value = row.get("fallback")
            fallback_id: str | None = None
            text_source = "script_evidence_matrix.voice_text"
            if fallback_value is not None:
                if not isinstance(fallback_value, Mapping):
                    raise ScriptCompileError(f"{fragment_id} fallback must be an object")
                fallback_id = fallback_value.get("fallback_id")  # type: ignore[assignment]
                if not isinstance(fallback_id, str) or fallback_id not in fallbacks:
                    raise ScriptCompileError(f"{fragment_id} uses unapproved fallback")
                fallback = fallbacks[fallback_id]
                if fallback["claim_id"] not in row_claims:
                    raise ScriptCompileError(f"{fragment_id} fallback exceeds claim boundary")
                text = str(fallback["text"])
                text_source = "mutation_plan.allowed_fallbacks"
            else:
                text = row.get("voice_text", "")
                if not isinstance(text, str):
                    raise ScriptCompileError(f"{fragment_id}.voice_text must be text")
            if not text.strip():
                continue
            if any(blocked and blocked in text for blocked in forbidden):
                raise ScriptCompileError(f"{fragment_id} exceeds Gate 2 claim boundary")
            lines.append(
                {
                    "line_id": f"line{len(lines) + 1:02d}",
                    "fragment_id": fragment_id,
                    "text": text,
                    "text_source": text_source,
                    "approved_claim_ids": row_claims,
                    "evidence_row_ref": fragment_id,
                    "selected_candidate_id": row.get("selected_candidate_id"),
                    "fallback_id": fallback_id,
                    "claim_boundary": "approved_claims_only",
                    "narrative_role": narrative_rows.get(fragment_id, {}).get("narrative_role"),
                    "continuity_before": narrative_rows.get(fragment_id, {}).get("continuity_before"),
                    "continuity_after": narrative_rows.get(fragment_id, {}).get("continuity_after"),
                    "coherence_status": narrative_rows.get(fragment_id, {}).get("coherence_status", "passed"),
                }
            )
        return {
            "artifact_type": "production_script_candidate",
            "schema_id": "urn:capcut:remix-reference-video:artifact:production-script-candidate",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "implementation_version": self.implementation_version,
            "lifecycle_status": "awaiting_user",
            "input_hashes": {name: self._sha256(path) for name, path in paths.items()},
            "lines": lines,
        }

    @staticmethod
    def _canonical_path(path: Path, expected_name: str) -> Path:
        requested = Path(path)
        if requested.name != expected_name:
            raise ScriptCompileError(f"input path must be {expected_name}")
        if requested.is_symlink():
            raise ScriptCompileError(f"{expected_name} must not be a symlink")
        return requested.resolve(strict=True)

    @staticmethod
    def _claim_ids(value: object) -> set[str]:
        if not isinstance(value, list):
            raise ScriptCompileError("baseline claims must be an array")
        result: set[str] = set()
        for row in value:
            if not isinstance(row, Mapping) or not isinstance(row.get("claim_id"), str):
                raise ScriptCompileError("baseline claim is invalid")
            result.add(str(row["claim_id"]))
        return result

    @staticmethod
    def _fragments(value: object) -> dict[str, Mapping[str, object]]:
        if not isinstance(value, list):
            raise ScriptCompileError("baseline fragments must be an array")
        result: dict[str, Mapping[str, object]] = {}
        for row in value:
            if not isinstance(row, Mapping) or not isinstance(row.get("fragment_id"), str):
                raise ScriptCompileError("baseline fragment is invalid")
            result[str(row["fragment_id"])] = row
        return result

    @staticmethod
    def _fallbacks(value: object) -> dict[str, Mapping[str, object]]:
        if not isinstance(value, list):
            raise ScriptCompileError("allowed_fallbacks must be an array")
        result: dict[str, Mapping[str, object]] = {}
        for row in value:
            if not isinstance(row, Mapping):
                raise ScriptCompileError("fallback is invalid")
            fallback_id, claim_id, text = row.get("fallback_id"), row.get("claim_id"), row.get("text")
            if not all(isinstance(item, str) and item for item in (fallback_id, claim_id, text)):
                raise ScriptCompileError("fallback is invalid")
            result[str(fallback_id)] = row
        return result

    @staticmethod
    def _string_list(value: object, field: str) -> list[str]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise ScriptCompileError(f"{field} must contain strings")
        return list(value)

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
