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
from .native_registry import NativeAdapterRegistry, NativeStageAdapter
from .storage import read_json_object


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

    blueprint_output = root / "shot_blueprint.json"
    baseline_output = root / "content_baseline.json"
    registry.register(
        NativeStageAdapter(
            root,
            execution_stage_id="compile-blueprint",
            implementation_version="blueprint-native-v1",
            required_inputs=(brief, recipe, precheck),
            declared_outputs=(blueprint_output, baseline_output),
            execute_fn=lambda payload: _compile_blueprint(
                brief, recipe, precheck, payload
            ),
            require_stage_input=True,
        )
    )

    mutation_output = root / "mutation_plan.json"
    registry.register(
        NativeStageAdapter(
            root,
            execution_stage_id="compile-mutation-plan",
            implementation_version="mutation-native-v1",
            required_inputs=(brief, baseline_output),
            declared_outputs=(mutation_output,),
            execute_fn=lambda payload: _compile_mutation(brief, baseline_output, payload),
            require_stage_input=True,
        )
    )

    coverage_output = root / "coverage_report.json"
    registry.register(
        NativeStageAdapter(
            root,
            execution_stage_id="build-coverage-authoritative",
            implementation_version="retrieval-coverage-native-v1",
            required_inputs=(baseline_output, profiles, state_file),
            declared_outputs=(coverage_output,),
            execute_fn=lambda _payload: _build_coverage(baseline_output, profiles, state_file),
        )
    )

    matches_output = root / "matches.json"
    registry.register(
        NativeStageAdapter(
            root,
            execution_stage_id="match-assets",
            implementation_version="retrieval-match-native-v1",
            required_inputs=(baseline_output, profiles, state_file),
            declared_outputs=(matches_output,),
            execute_fn=lambda _payload: _match_assets(baseline_output, profiles, state_file),
        )
    )
    return registry


def _compile_blueprint(
    brief_path: Path, recipe_path: Path, precheck_path: Path, payload: Mapping[str, object]
) -> dict[str, object]:
    compiled = BlueprintAdapter().compile(
        brief=read_json_object(brief_path),
        recipe=read_json_object(recipe_path),
        coverage_precheck=read_json_object(precheck_path),
        target_fragments=_required_list(payload, "target_fragments"),
    )
    return compiled


def _compile_mutation(
    brief_path: Path, baseline_path: Path, payload: Mapping[str, object]
) -> Mapping[str, object]:
    return ControlledMutationAdapter().compile(
        brief=read_json_object(brief_path),
        content_baseline=read_json_object(baseline_path),
        fallback_ids=_required_list(payload, "fallback_ids"),
    )


def _build_coverage(
    baseline_path: Path, profiles_path: Path, state_path: Path
) -> Mapping[str, object]:
    return RetrievalAdapter().build_coverage(
        scope="authoritative",
        content_baseline=read_json_object(baseline_path),
        asset_profiles=_required_list(read_json_object(profiles_path), "asset_profiles"),
        gate2_approved=_gate_approved(state_path, "gate2"),
    )


def _match_assets(
    baseline_path: Path, profiles_path: Path, state_path: Path
) -> Mapping[str, object]:
    return RetrievalAdapter().match_assets(
        content_baseline=read_json_object(baseline_path),
        asset_profiles=_required_list(read_json_object(profiles_path), "asset_profiles"),
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


__all__ = ["register_planning_adapters"]
