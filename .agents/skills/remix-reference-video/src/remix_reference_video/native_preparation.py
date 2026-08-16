"""Native bindings for precheck and the atomic Gate 2 review package."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from .adapters.mutation import ControlledMutationAdapter
from .adapters.retrieval import RetrievalAdapter
from .native_registry import NativeAdapterRegistry, NativeStageAdapter
from .storage import read_json_object


def register_preparation_adapters(
    registry: NativeAdapterRegistry,
    *,
    asset_profiles_path: Path,
    blueprint_stage_input_path: Path,
) -> NativeAdapterRegistry:
    root = registry.task_root
    profiles = Path(asset_profiles_path)
    blueprint_input = Path(blueprint_stage_input_path)
    precheck = root / "coverage_precheck.json"
    registry.register(
        NativeStageAdapter(
            root,
            execution_stage_id="build-coverage-precheck",
            implementation_version="coverage-precheck-native-v1",
            required_inputs=(profiles, blueprint_input),
            declared_outputs=(precheck,),
            execute_fn=lambda: _precheck(profiles, blueprint_input),
        )
    )
    baseline = root / "content_baseline.json"
    mutation = root / "mutation_plan.json"
    state = root / "pipeline_state.json"
    package = root / "gate_review_packages" / "gate2.json"
    registry.register(
        NativeStageAdapter(
            root,
            execution_stage_id="lint-gate2-package",
            implementation_version="gate2-package-native-v1",
            required_inputs=(baseline, mutation, state),
            declared_outputs=(package,),
            execute_fn=lambda: _gate2_package(root, baseline, mutation, state),
        )
    )
    return registry


def _precheck(profiles_path: Path, stage_input_path: Path) -> Mapping[str, object]:
    handoff = json.loads(Path(stage_input_path).read_text(encoding="utf-8"))
    payload = handoff.get("payload")
    fragments = payload.get("target_fragments") if isinstance(payload, Mapping) else None
    if not isinstance(fragments, list):
        raise ValueError("compile-blueprint target_fragments are required for precheck")
    baseline = {
        "artifact_type": "content_baseline",
        "fragments": [row for row in fragments if isinstance(row, Mapping)],
    }
    profiles = read_json_object(profiles_path).get("asset_profiles")
    if not isinstance(profiles, list):
        raise ValueError("asset_profiles are required")
    return RetrievalAdapter().build_coverage(
        scope="precheck",
        content_baseline=baseline,
        asset_profiles=[row for row in profiles if isinstance(row, Mapping)],
        gate2_approved=False,
    )


def _gate2_package(
    root: Path, baseline: Path, mutation: Path, state_path: Path
) -> Mapping[str, object]:
    state = read_json_object(state_path)
    return ControlledMutationAdapter().build_gate2_package(
        content_baseline_path=baseline,
        mutation_plan_path=mutation,
        run_id=str(state["run_id"]),
        state_revision=int(state["state_revision"]),
        created_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    )


__all__ = ["register_preparation_adapters"]
