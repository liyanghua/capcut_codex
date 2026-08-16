"""Compile Controlled Mutation drafts and atomic Gate 2 review packages."""

from __future__ import annotations

import hashlib
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
