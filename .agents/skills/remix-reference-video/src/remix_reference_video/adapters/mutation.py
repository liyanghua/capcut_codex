"""Compile Controlled Mutation drafts and atomic Gate 2 review packages."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ..storage import read_json_object


class MutationValidationError(ValueError):
    """Raised when a mutation exceeds the approved Brief or baseline."""


_ENVELOPE = {
    "schema_version": "1.0.0",
    "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
}
_DOWNSTREAM_ARTIFACTS = (
    "coverage_report.json",
    "matches.json",
    "fragment_plan.json",
    "script_evidence_matrix.json",
    "production_script_candidate.json",
    "approved_production_script.json",
    "material_manifest.json",
    "reconstruction_timeline.json",
    "captions.srt",
    "remix.mp4",
    "final_validation_report.json",
)
_GATE2_CHANGE_COMPONENTS = frozenset(
    {"brief", "content_baseline", "mutation_plan", "claim_boundary", "fallback"}
)


class ControlledMutationAdapter:
    implementation_version = "controlled-mutation-adapter-v1"

    def compile(
        self,
        *,
        brief: Mapping[str, object],
        content_baseline: Mapping[str, object],
        fallback_ids: Sequence[str],
    ) -> dict[str, Any]:
        if content_baseline.get("artifact_type") != "content_baseline":
            raise MutationValidationError("content_baseline artifact is required")
        rows = brief.get("approved_fallbacks", [])
        if not isinstance(rows, list):
            raise MutationValidationError("approved_fallbacks must be an array")
        approved: dict[str, dict[str, object]] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise MutationValidationError("approved fallback must be an object")
            fallback_id = row.get("fallback_id")
            claim_id, text = row.get("claim_id"), row.get("text")
            if not all(isinstance(item, str) and item for item in (fallback_id, claim_id, text)):
                raise MutationValidationError("approved fallback is incomplete")
            approved[str(fallback_id)] = dict(row)
        selected: list[dict[str, object]] = []
        for fallback_id in fallback_ids:
            if fallback_id not in approved:
                raise MutationValidationError(f"unapproved fallback: {fallback_id}")
            selected.append(approved[fallback_id])
        return {
            **_ENVELOPE,
            "artifact_type": "mutation_plan",
            "schema_id": "urn:capcut:remix-reference-video:artifact:mutation-plan",
            "implementation_version": self.implementation_version,
            "lifecycle_status": "draft",
            "allowed_fallbacks": selected,
            "forbidden_claims": list(content_baseline.get("forbidden_claims", [])),
            "structural_requests": [],
        }

    def build_remix_strategy_candidates(
        self,
        *,
        content_baseline: Mapping[str, object],
        coverage_precheck: Mapping[str, object],
        creative_objective: Mapping[str, object],
        selected_decomposition_id: str,
    ) -> dict[str, Any]:
        """Build bounded, comparable Gate 2 remix options from advisory coverage."""
        if content_baseline.get("artifact_type") != "content_baseline":
            raise MutationValidationError("content_baseline artifact is required")
        if coverage_precheck.get("artifact_type") != "coverage_precheck" or coverage_precheck.get("scope") != "precheck":
            raise MutationValidationError("coverage_precheck advisory artifact is required")
        if creative_objective.get("artifact_type") != "creative_objective" or not isinstance(creative_objective.get("objective_id"), str):
            raise MutationValidationError("creative_objective artifact is required")
        if not isinstance(selected_decomposition_id, str) or not selected_decomposition_id:
            raise MutationValidationError("selected decomposition is required")
        fragments = content_baseline.get("fragments")
        if not isinstance(fragments, list):
            raise MutationValidationError("content baseline fragments are required")
        fragment_ids = [str(row["fragment_id"]) for row in fragments if isinstance(row, Mapping) and isinstance(row.get("fragment_id"), str)]
        coverage = coverage_precheck.get("coverage")
        coverage_rows = coverage if isinstance(coverage, list) else []
        viable = sum(1 for row in coverage_rows if isinstance(row, Mapping) and row.get("status") in {"likely", "covered", "available"})
        denominator = len(coverage_rows) or len(fragment_ids)
        estimate = round(viable / denominator, 6) if denominator else 0.0
        missing = [
            str(row.get("fragment_id"))
            for row in coverage_rows
            if isinstance(row, Mapping) and row.get("status") not in {"likely", "covered", "available"} and isinstance(row.get("fragment_id"), str)
        ]
        candidates = [
            self._candidate("balanced_remix_v1", fragment_ids, missing, estimate, 0.25),
            self._candidate("structure_fidelity_v1", fragment_ids, missing, estimate, 0.10),
            self._candidate("asset_constrained_v1", fragment_ids, missing, estimate, 0.55 if missing else 0.20),
        ]
        return {
            **_ENVELOPE,
            "artifact_type": "remix_strategy_candidates",
            "schema_id": "urn:capcut:remix-reference-video:artifact:remix-strategy-candidates",
            "implementation_version": "remix-strategy-builder-v1",
            "lifecycle_status": "ready",
            "input_hashes": {
                "content_baseline.json": self._digest(content_baseline),
                "coverage_precheck.json": self._digest(coverage_precheck),
                "creative_objective.json": self._digest(creative_objective),
            },
            "objective_id": creative_objective["objective_id"],
            "selected_decomposition_id": selected_decomposition_id,
            "candidates": candidates,
        }

    @staticmethod
    def _candidate(
        strategy_id: str,
        fragment_ids: list[str],
        missing: list[str],
        estimate: float,
        deviation: float,
    ) -> dict[str, object]:
        available = [item for item in fragment_ids if item not in missing]
        return {
            "strategy_id": strategy_id,
            "status": "passed",
            "preserve": available,
            "replace": missing,
            "compress": missing if strategy_id == "asset_constrained_v1" else [],
            "expand": [fragment_ids[0]] if fragment_ids and strategy_id == "conversion_adaptation_v1" else [],
            "reorder": [],
            "fallback": missing,
            "coverage_estimate": estimate,
            "feasibility_estimate": estimate,
            "reference_deviation_estimate": deviation,
        }

    @staticmethod
    def _digest(value: object) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def build_gate2_package(
        self,
        *,
        content_baseline_path: Path,
        mutation_plan_path: Path,
        run_id: str,
        state_revision: int,
        created_at: str,
    ) -> dict[str, Any]:
        if not isinstance(run_id, str) or not run_id:
            raise MutationValidationError("run_id is required")
        if isinstance(state_revision, bool) or not isinstance(state_revision, int) or state_revision < 0:
            raise MutationValidationError("state_revision must be nonnegative")
        if not isinstance(created_at, str) or not created_at:
            raise MutationValidationError("created_at is required")
        baseline_path = Path(content_baseline_path)
        mutation_path = Path(mutation_plan_path)
        if baseline_path.name != "content_baseline.json":
            raise MutationValidationError("content baseline path must be content_baseline.json")
        if mutation_path.name != "mutation_plan.json":
            raise MutationValidationError("mutation path must be mutation_plan.json")
        content_baseline = read_json_object(baseline_path)
        mutation_plan = read_json_object(mutation_path)
        if content_baseline.get("artifact_type") != "content_baseline":
            raise MutationValidationError("content_baseline artifact is required")
        if mutation_plan.get("artifact_type") != "mutation_plan":
            raise MutationValidationError("mutation_plan artifact is required")
        hashes = {
            "content_baseline.json": _file_hash(baseline_path),
            "mutation_plan.json": _file_hash(mutation_path),
        }
        return {
            **_ENVELOPE,
            "artifact_type": "gate_review_package",
            "schema_id": "urn:capcut:remix-reference-video:artifact:gate-review-package",
            "gate_id": "gate2",
            "approval_mode": "atomic",
            "run_id": run_id,
            "state_revision": state_revision,
            "created_at": created_at,
            "input_hashes": hashes,
            "lifecycle_status": "awaiting_user",
        }


def gate2_stale_projection(changed_components: Iterable[str]) -> dict[str, object]:
    changed = set(changed_components)
    if not changed.intersection(_GATE2_CHANGE_COMPONENTS):
        return {"gate_status": {}, "derived_artifacts": []}
    gates = (
        "gate2",
        "gate3_material_selection",
        "gate3_evidence_closure",
        "gate3",
        "gate4_pre_generation",
        "gate4_post_generation",
        "gate4",
        "gate5",
    )
    return {
        "gate_status": {gate: "stale" for gate in gates},
        "derived_artifacts": list(_DOWNSTREAM_ARTIFACTS),
    }


def _file_hash(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
