"""Native Runner bindings for the Blueprint, Mutation and Retrieval adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping
from datetime import UTC, datetime

from .adapters.blueprint import BlueprintAdapter
from .adapters.decomposition import DecompositionAdapter
from .adapters.mutation import ControlledMutationAdapter
from .adapters.retrieval import RetrievalAdapter
from .decomposition_handoff import build_gate1_package, materialize_approved_decomposition
from .material_evidence import build_material_evidence_requirements, merge_material_evidence
from .native_registry import NativeAdapterRegistry, NativeStageAdapter
from .storage import atomic_write_json, read_json_object


def register_planning_adapters(
    registry: NativeAdapterRegistry,
    *,
    brief_path: Path,
    recipe_path: Path,
    coverage_precheck_path: Path,
    asset_profiles_path: Path,
    state_path: Path | None = None,
) -> NativeAdapterRegistry:
    """Register real B2/B3 adapter calls on a task-local native registry.

    Inputs are explicit so the registry cannot silently discover arbitrary task
    files. Stage decisions still arrive through ``stage_inputs`` and Gate state
    is read only from ``pipeline_state.json``.
    """

    root = registry.task_root
    state_file = state_path or root / "pipeline_state.json"
    brief = Path(brief_path)
    recipe = Path(recipe_path)
    precheck = Path(coverage_precheck_path)
    profiles = Path(asset_profiles_path)
    for path in (brief, recipe, precheck, profiles, state_file):
        if path.resolve(strict=False).parent != root and root not in path.resolve(strict=False).parents:
            raise ValueError(f"planning input escapes task root: {path}")

    decomposition_output = root / "decomposition_bundle.json"
    gate1_package = root / "gate_review_packages" / "gate1.json"
    registry.register(NativeStageAdapter(
        root,
        execution_stage_id="build-decomposition-candidates",
        implementation_version="decomposition-native-v1",
        required_inputs=(recipe,),
        declared_outputs=(decomposition_output,),
        execute_fn=lambda: DecompositionAdapter().build(read_json_object(recipe)),
    ))
    registry.register(NativeStageAdapter(
        root,
        execution_stage_id="build-gate1-package",
        implementation_version="gate1-creative-package-v1",
        required_inputs=(recipe, decomposition_output, state_file),
        declared_outputs=(gate1_package,),
        execute_fn=lambda: build_gate1_package(root),
    ))
    registry.register(NativeStageAdapter(
        root,
        execution_stage_id="materialize-approved-decomposition",
        implementation_version="decomposition-handoff-v1",
        required_inputs=(brief, decomposition_output, gate1_package, state_file),
        declared_outputs=(
            root / "derived" / "gate1_decomposition_selection.json",
            root / "stage_inputs" / "compile-blueprint.json",
            root / "stage_inputs" / "compile-mutation-plan.json",
        ),
        execute_fn=lambda: materialize_approved_decomposition(root),
        domain_managed_outputs=True,
    ))

    creative = False
    snapshot = root / "g_b_frozen_input_snapshot.json"
    if snapshot.is_file() and not snapshot.is_symlink():
        creative = read_json_object(snapshot).get("creative_contract_version") == "creative_contract_v1"

    blueprint_output = root / "shot_blueprint.json"
    baseline_output = root / "content_baseline.json"
    objective_output = root / "creative_objective.json"
    blueprint_outputs = (blueprint_output, baseline_output, objective_output) if creative else (blueprint_output, baseline_output)
    registry.register(
        NativeStageAdapter(
            root,
            execution_stage_id="compile-blueprint",
            implementation_version="blueprint-native-v2" if creative else "blueprint-native-v1",
            required_inputs=(brief, recipe, precheck),
            declared_outputs=blueprint_outputs,
            execute_fn=lambda payload: _compile_blueprint(
                brief, recipe, precheck, payload, creative=creative,
                gate1_selection_hash=_file_hash(root / "derived" / "gate1_decomposition_selection.json") if creative else None,
            ),
            require_stage_input=True,
        )
    )

    mutation_output = root / "mutation_plan.json"
    strategy_output = root / "remix_strategy_candidates.json"
    mutation_outputs = (mutation_output, strategy_output) if creative else (mutation_output,)
    registry.register(
        NativeStageAdapter(
            root,
            execution_stage_id="compile-mutation-plan",
            implementation_version="mutation-native-v2" if creative else "mutation-native-v1",
            required_inputs=(brief, baseline_output, precheck, objective_output) if creative else (brief, baseline_output),
            declared_outputs=mutation_outputs,
            execute_fn=lambda payload: _compile_mutation(
                brief, baseline_output, precheck, objective_output, payload, creative=creative,
            ),
            require_stage_input=True,
        )
    )

    evidence_requirements = root / "material_evidence_requirements.json"
    evidence_annotations = root / "material_evidence_annotations.json"
    evidence_profiles = root / "derived" / "material_evidence_profiles.json"
    if creative:
        registry.register(NativeStageAdapter(
            root,
            execution_stage_id="build-material-evidence-requirements",
            implementation_version="material-evidence-v1",
            required_inputs=(baseline_output, profiles, state_file),
            declared_outputs=(evidence_requirements, evidence_profiles),
            execute_fn=lambda: _build_material_evidence(
                baseline_output, profiles, evidence_annotations, evidence_requirements, evidence_profiles
            ),
            domain_managed_outputs=True,
        ))
    retrieval_profiles = evidence_profiles if creative else profiles
    coverage_output = root / "coverage_report.json"
    registry.register(
        NativeStageAdapter(
            root,
            execution_stage_id="build-coverage-authoritative",
            implementation_version="retrieval-coverage-native-v1",
            required_inputs=(baseline_output, retrieval_profiles, state_file),
            declared_outputs=(coverage_output,),
            execute_fn=lambda _payload: _build_coverage(baseline_output, retrieval_profiles, state_file),
        )
    )

    matches_output = root / "matches.json"
    registry.register(
        NativeStageAdapter(
            root,
            execution_stage_id="match-assets",
            implementation_version="retrieval-match-native-v1",
            required_inputs=(baseline_output, retrieval_profiles, state_file),
            declared_outputs=(matches_output,),
            execute_fn=lambda _payload: _match_assets(baseline_output, retrieval_profiles, state_file),
        )
    )
    return registry


def _build_material_evidence(
    baseline_path: Path,
    profiles_path: Path,
    annotations_path: Path,
    requirements_path: Path,
    evidence_profiles_path: Path,
) -> Mapping[str, object]:
    baseline = read_json_object(baseline_path)
    profiles_artifact = read_json_object(profiles_path)
    profiles = _required_list(profiles_artifact, "asset_profiles")
    annotations = read_json_object(annotations_path) if annotations_path.is_file() else None
    if annotations is not None:
        hashes = annotations.get("input_hashes")
        if not isinstance(hashes, Mapping) or hashes.get("asset_profiles.json") != _file_hash(profiles_path):
            raise ValueError("material evidence annotation profile hash is stale")
        if not requirements_path.is_file() or hashes.get("material_evidence_requirements.json") != _file_hash(requirements_path):
            raise ValueError("material evidence requirements hash is stale")
    requirements = build_material_evidence_requirements(baseline, profiles, annotations)
    merged = merge_material_evidence(profiles, annotations)
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_profiles_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(requirements_path, requirements)
    atomic_write_json(evidence_profiles_path, {
        "artifact_type": "material_evidence_profiles", "profiles": merged["profiles"],
        "input_hashes": requirements["input_hashes"],
    })
    if requirements["status"] != "ready":
        return {
            "status": "recoverable_pause", "active_stage": "collect-material-evidence",
            "blocker": {
                "category": "manual_classification_required", "requires_user": True,
                "detail": "需要补充素材的产品、语义、动作、叠字和证据窗",
                "requirements_sha256": _file_hash(requirements_path),
                "asset_profiles_sha256": _file_hash(profiles_path),
            },
            "next_actions": ["submit_material_evidence"],
        }
    return {"status": "succeeded"}


def _compile_blueprint(
    brief_path: Path,
    recipe_path: Path,
    precheck_path: Path,
    payload: Mapping[str, object],
    *,
    creative: bool = False,
    gate1_selection_hash: str | None = None,
) -> dict[str, object]:
    brief = read_json_object(brief_path)
    compiled = BlueprintAdapter().compile(
        brief=brief,
        recipe=read_json_object(recipe_path),
        coverage_precheck=read_json_object(precheck_path),
        target_fragments=_required_list(payload, "target_fragments"),
    )
    if creative:
        selected = payload.get("selected_decomposition_id")
        if not isinstance(selected, str) or not selected:
            raise ValueError("creative Blueprint requires selected decomposition")
        if gate1_selection_hash is None:
            raise ValueError("creative Blueprint requires Gate 1 selection hash")
        compiled["creative_objective"] = BlueprintAdapter().build_creative_objective(
            brief=brief,
            selected_decomposition_id=selected,
            gate1_selection_hash=gate1_selection_hash,
        )
    return compiled


def _compile_mutation(
    brief_path: Path,
    baseline_path: Path,
    precheck_path: Path | None,
    objective_path: Path | None,
    payload: Mapping[str, object],
    *,
    creative: bool = False,
) -> Mapping[str, object]:
    adapter = ControlledMutationAdapter()
    baseline = read_json_object(baseline_path)
    mutation = adapter.compile(
        brief=read_json_object(brief_path),
        content_baseline=baseline,
        fallback_ids=_required_list(payload, "fallback_ids"),
    )
    if not creative:
        return mutation
    if precheck_path is None or objective_path is None:
        raise ValueError("creative Mutation requires objective and coverage precheck")
    selected = payload.get("selected_decomposition_id")
    if not isinstance(selected, str) or not selected:
        raise ValueError("creative Mutation requires selected decomposition")
    return {
        "mutation_plan": mutation,
        "remix_strategy_candidates": adapter.build_remix_strategy_candidates(
            content_baseline=baseline,
            coverage_precheck=read_json_object(precheck_path),
            creative_objective=read_json_object(objective_path),
            selected_decomposition_id=selected,
        ),
    }


def _build_coverage(
    baseline_path: Path, profiles_path: Path, state_path: Path
) -> Mapping[str, object]:
    return RetrievalAdapter().build_coverage(
        scope="authoritative",
        content_baseline=read_json_object(baseline_path),
        asset_profiles=_profiles_for_retrieval(profiles_path),
        gate2_approved=_gate_approved(state_path, "gate2"),
    )


def _match_assets(
    baseline_path: Path, profiles_path: Path, state_path: Path
) -> Mapping[str, object]:
    return RetrievalAdapter().match_assets(
        content_baseline=read_json_object(baseline_path),
        asset_profiles=_profiles_for_retrieval(profiles_path),
        gate2_approved=_gate_approved(state_path, "gate2"),
    )


def _file_hash(path: Path) -> str:
    import hashlib
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _gate_approved(path: Path, gate_id: str) -> bool:
    state = read_json_object(path)
    gates = state.get("gate_status")
    return isinstance(gates, Mapping) and gates.get(gate_id) == "approved"


def _required_list(value: object, field: str) -> list[Mapping[str, object]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, Mapping)]
    if isinstance(value, Mapping) and isinstance(value.get(field), list):
        return [row for row in value[field] if isinstance(row, Mapping)]
    raise ValueError(f"{field} must be an array of objects")


def _profiles_for_retrieval(path: Path) -> list[Mapping[str, object]]:
    value = read_json_object(path)
    field = "profiles" if value.get("artifact_type") == "material_evidence_profiles" else "asset_profiles"
    return _required_list(value, field)


__all__ = ["register_planning_adapters"]
