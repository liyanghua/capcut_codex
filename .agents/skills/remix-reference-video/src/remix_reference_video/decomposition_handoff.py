"""Hash-bound handoff from an approved Gate 1 decomposition to Blueprint."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

from .storage import StorageError, atomic_write_json, read_json_object


_ENVELOPE = {
    "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
}
_ROLE_ACTIONS = (
    ("开场情境", "show_context"), ("问题/需求", "show_problem"),
    ("产品出现", "show_product"), ("功能证明", "demonstrate_feature"),
    ("使用结果", "show_result"), ("收束", "close"),
)


class DecompositionHandoffError(ValueError):
    pass


def _sha(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build_gate1_package(task_root: Path) -> dict[str, object]:
    root = Path(task_root).resolve(strict=True)
    state = read_json_object(root / "pipeline_state.json")
    bundle_path = root / "decomposition_bundle.json"
    recipe_path = root / "recipe.json"
    bundle = read_json_object(bundle_path)
    candidates = bundle.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise DecompositionHandoffError("decomposition candidates are required")
    bundle_hash = _sha(bundle_path)
    return {
        **_ENVELOPE, "artifact_type": "gate_review_package",
        "schema_id": "urn:capcut:remix-reference-video:artifact:gate-review-package",
        "gate_id": "gate1", "run_id": state["run_id"], "state_revision": state["state_revision"],
        "created_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "input_hashes": {"recipe.json": _sha(recipe_path), "decomposition_bundle.json": bundle_hash},
        "creative_bindings": {
            "decomposition_bundle.json_sha256": bundle_hash,
            "strategy_registry_version": "decomposition_handoff_v1",
        },
    }


def materialize_approved_decomposition(task_root: Path) -> dict[str, object]:
    root = Path(task_root).resolve(strict=True)
    state = read_json_object(root / "pipeline_state.json")
    if not isinstance(state.get("gate_status"), Mapping) or state["gate_status"].get("gate1") != "approved":
        raise DecompositionHandoffError("Gate 1 is not approved")
    decisions = [
        row for row in state.get("decisions", [])
        if isinstance(row, Mapping) and row.get("gate_id") == "gate1" and row.get("decision") == "approved"
    ]
    if not decisions:
        raise DecompositionHandoffError("current approved Gate 1 decision is required")
    decision = decisions[-1]
    strategy = decision.get("strategy")
    selected_id = strategy.get("selected_decomposition_id") if isinstance(strategy, Mapping) else None
    if not isinstance(selected_id, str) or not selected_id:
        raise DecompositionHandoffError("approved decision has no selected decomposition")
    bundle_path = root / "decomposition_bundle.json"
    brief_path = root / "project_brief.json"
    bundle_hash = _sha(bundle_path)
    input_hashes = decision.get("input_hashes")
    if not isinstance(input_hashes, Mapping) or input_hashes.get("decomposition_bundle.json") != bundle_hash:
        raise DecompositionHandoffError("approved decomposition bundle hash is not current")
    package_path = root / "gate_review_packages" / "gate1.json"
    if decision.get("review_package_hash") != _sha(package_path):
        raise DecompositionHandoffError("approved Gate 1 package hash is not current")
    bundle = read_json_object(bundle_path)
    selected = next(
        (row for row in bundle.get("candidates", []) if isinstance(row, Mapping) and row.get("decomposition_id") == selected_id),
        None,
    )
    if not isinstance(selected, Mapping):
        raise DecompositionHandoffError("selected decomposition is not present in current bundle")
    brief = read_json_object(brief_path)
    claims = brief.get("approved_claims")
    if not isinstance(claims, list) or any(
        not isinstance(row, Mapping) or not isinstance(row.get("claim_id"), str) or not isinstance(row.get("text"), str)
        for row in claims
    ):
        raise DecompositionHandoffError("frozen approved claims are required")
    segments = selected.get("segments")
    if not isinstance(segments, list) or not segments:
        raise DecompositionHandoffError("selected decomposition segments are required")
    fragments: list[dict[str, object]] = []
    for index, segment in enumerate(segments):
        if not isinstance(segment, Mapping):
            raise DecompositionHandoffError("selected decomposition segment is invalid")
        role_index = 0 if index == 0 else (5 if index == len(segments) - 1 else min(3, index + 1))
        role, action = _ROLE_ACTIONS[role_index]
        claim = claims[index % len(claims)] if claims else None
        fragment: dict[str, object] = {
            "fragment_id": f"fragment{index + 1:02d}",
            "claim_ids": [claim["claim_id"]] if isinstance(claim, Mapping) else [],
            "narration": str(claim["text"]) if isinstance(claim, Mapping) else "",
            "narrative_role": role, "required_actions": [action],
            "selected_decomposition_id": selected_id,
            "decomposition_segment_id": segment.get("segment_id"),
            "strategy_id": selected.get("strategy_id"),
            "strategy_version": "decomposition_handoff_v1",
            "requirements": {
                "product_type": str(brief.get("product", {}).get("name", "")) if isinstance(brief.get("product"), Mapping) else "",
                "required_semantics": [claim["claim_id"]] if isinstance(claim, Mapping) else [],
                "required_actions": [action],
                "allowed_media_types": ["image", "video"],
                "forbidden_semantics": [],
                "expected_visual_seconds": 1.0,
            },
        }
        for name in ("reference_shot_id", "start_seconds", "end_seconds"):
            if name in segment:
                fragment[name] = segment[name]
        fragments.append(fragment)
    derived = root / "derived"
    derived.mkdir(exist_ok=True)
    selection_path = derived / "gate1_decomposition_selection.json"
    atomic_write_json(selection_path, {
        "decision_id": decision.get("decision_id"), "selected_decomposition_id": selected_id,
        "strategy_id": selected.get("strategy_id"), "decomposition_bundle_sha256": bundle_hash,
        "review_package_hash": decision.get("review_package_hash"),
    })
    hashes = {
        "derived/gate1_decomposition_selection.json": _sha(selection_path),
        "decomposition_bundle.json": bundle_hash, "project_brief.json": _sha(brief_path),
    }
    stage_inputs = root / "stage_inputs"
    stage_inputs.mkdir(exist_ok=True)
    common = {
        **_ENVELOPE, "artifact_type": "stage_input",
        "schema_id": "urn:capcut:remix-reference-video:artifact:stage-input",
        "producer": {"stage_id": "materialize-approved-decomposition", "implementation_version": "decomposition_handoff_v1"},
        "created_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "lifecycle_status": "awaiting_user", "input_hashes": hashes,
    }
    atomic_write_json(stage_inputs / "compile-blueprint.json", {
        **common, "stage_id": "compile-blueprint",
        "payload": {"selected_decomposition_id": selected_id, "target_fragments": fragments},
    })
    atomic_write_json(stage_inputs / "compile-mutation-plan.json", {
        **common, "stage_id": "compile-mutation-plan",
        "payload": {"selected_decomposition_id": selected_id, "fallback_ids": []},
    })
    return {"selected_decomposition_id": selected_id, "fragment_count": len(fragments)}


__all__ = ["DecompositionHandoffError", "build_gate1_package", "materialize_approved_decomposition"]
