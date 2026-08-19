"""Native Runner bindings for Gate 3 through Gate 5."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from .adapters.gate3 import Gate3Adapter
from .adapters.reconstruction import ReconstructionAdapter
from .adapters.render import RenderAdapter
from .adapters.retrieval import RetrievalAdapter
from .adapters.script_compile import ProductionScriptCompiler
from .artifact_validator import ArtifactValidator
from .narrative_coherence import NARRATIVE_CONTRACT_VERSION, NarrativeCoherenceBuilder
from .native_registry import NativeAdapterRegistry, NativeStageAdapter
from .storage import StorageError, TaskStorage, atomic_write_json, read_json_object
from .timeline import TimelineBuilder
from .visual_layout import VisualLayoutBuilder
from .voice import VoiceGenerator, VoiceProvider
from .voice_preflight import VoicePreflight


def _approved_script_path(root: Path) -> Path:
    try:
        state = read_json_object(root / "pipeline_state.json")
        artifact = state.get("artifacts", {}).get("approved_production_script")
        if isinstance(artifact, Mapping) and isinstance(artifact.get("path"), str):
            candidate = (root / artifact["path"]).resolve(strict=True)
            if root in candidate.parents and not candidate.is_symlink():
                return candidate
    except (OSError, KeyError, TypeError, ValueError, StorageError):
        pass
    return root / "approved_production_script.json"


def _fragment_plan_path(root: Path) -> Path:
    base = root / "fragment_plan.json"
    if not base.exists():
        return base
    try:
        revision = int(read_json_object(root / "pipeline_state.json")["state_revision"])
    except (OSError, KeyError, TypeError, ValueError, StorageError):
        return base
    return root / "versions" / "fragment_plan" / f"r{revision}" / "fragment_plan.json"


def register_completion_adapters(
    registry: NativeAdapterRegistry,
    *,
    asset_root: Path,
    voice_provider: VoiceProvider,
    voice_duration: Callable[[Path], float],
    proxy_renderer: Callable[..., Mapping[str, object]],
    boundary_frame_times: Callable[[Path], Sequence[float]],
    final_renderer: Callable[..., Mapping[str, object]],
    media_probe: Callable[[Path], Mapping[str, object]],
    archive_root: Path | None = None,
) -> NativeAdapterRegistry:
    """Register real Gate 3/B4/B5 calls on an isolated native registry."""

    root = registry.task_root
    assets = Path(asset_root).resolve(strict=True)
    state = root / "pipeline_state.json"
    candidate = root / "material_selection_candidate.json"
    matches = root / "matches.json"
    baseline = root / "content_baseline.json"
    blueprint = root / "shot_blueprint.json"
    mutation = root / "mutation_plan.json"
    fragment_plan = _fragment_plan_path(root)
    evidence = root / "script_evidence_matrix.json"
    narrative_report = root / "narrative_coherence_report.json"
    visual_report = root / "visual_layout_report.json"
    asset_profiles = root / "asset_profiles.json"
    script_candidate = root / "production_script_candidate.json"
    baseline_contract = None
    if baseline.is_file() and not baseline.is_symlink():
        try:
            baseline_contract = read_json_object(baseline).get("narrative_contract_version")
        except (OSError, StorageError):
            baseline_contract = None
    script_inputs: tuple[Path, ...] = (baseline, mutation, evidence, state)
    if baseline_contract == NARRATIVE_CONTRACT_VERSION:
        script_inputs = (baseline, mutation, evidence, narrative_report, state)
    material = root / "material_manifest.json"
    approved_script = _approved_script_path(root)
    voice_preflight = root / "voice_preflight.json"
    voice_manifest = root / "voice" / "voice_manifest.json"
    duration_report = root / "voice" / "duration_report.json"
    timeline = root / "reconstruction_timeline.json"
    captions = root / "captions.srt"

    registry.register(NativeStageAdapter(
        root, execution_stage_id="build-material-selection-package",
        implementation_version="gate3-selection-native-v1",
        required_inputs=(matches, state),
        declared_outputs=(candidate, root / "gate_review_packages" / "gate3_material_selection.json"),
        execute_fn=lambda payload: _selection_package(root, matches, candidate, payload),
        require_stage_input=True,
    ))
    registry.register(NativeStageAdapter(
        root, execution_stage_id="freeze-fragment-plan",
        implementation_version="gate3-freeze-native-v1",
        required_inputs=(candidate, state), declared_outputs=(fragment_plan,),
        execute_fn=lambda _payload: _freeze_plan(root, candidate),
    ))
    registry.register(NativeStageAdapter(
        root, execution_stage_id="validate-script-evidence",
        implementation_version="gate3-evidence-native-v1",
        required_inputs=(baseline, fragment_plan, state),
        declared_outputs=(evidence, root / "gate_review_packages" / "gate3_evidence_closure.json"),
        execute_fn=lambda payload: _evidence_package(root, baseline, fragment_plan, evidence, payload),
        require_stage_input=True,
    ))
    registry.register(NativeStageAdapter(
        root, execution_stage_id="summarize-gate3",
        implementation_version="gate3-summary-native-v1",
        required_inputs=(state,), declared_outputs=(),
        execute_fn=lambda: {"status": Gate3Adapter.summarize_gate3(_gates(root))},
    ))
    registry.register(NativeStageAdapter(
        root, execution_stage_id="build-narrative-coherence",
        implementation_version="narrative-coherence-native-v1",
        required_inputs=(baseline, mutation, blueprint, evidence, state),
        declared_outputs=(narrative_report,),
        execute_fn=lambda: _run_narrative_coherence(root, baseline, mutation, blueprint, evidence, narrative_report),
    ))
    registry.register(NativeStageAdapter(
        root, execution_stage_id="build-production-script",
        implementation_version="script-compile-native-v2",
        required_inputs=script_inputs, declared_outputs=(script_candidate,),
        execute_fn=lambda: _compile_script(root, baseline, mutation, evidence, narrative_report),
    ))
    registry.register(NativeStageAdapter(
        root, execution_stage_id="materialize-approved-broad",
        implementation_version="materialize-native-v1",
        required_inputs=(fragment_plan,), declared_outputs=(material,),
        execute_fn=lambda: ReconstructionAdapter(root, assets).materialize_approved_broad(
            fragment_plan_path=fragment_plan
        ),
    ))
    registry.register(NativeStageAdapter(
        root, execution_stage_id="validate-visual-layout",
        implementation_version="visual-layout-native-v1",
        required_inputs=(fragment_plan, asset_profiles, material, state),
        declared_outputs=(visual_report,),
        execute_fn=lambda: _run_visual_layout(root, fragment_plan, asset_profiles, material, visual_report),
    ))
    gate4_pre = root / "gate_review_packages" / "gate4_pre_generation.json"
    registry.register(NativeStageAdapter(
        root, execution_stage_id="voice-preflight",
        implementation_version="voice-preflight-native-v1",
        required_inputs=(script_candidate, fragment_plan), declared_outputs=(voice_preflight,),
        execute_fn=lambda payload: _run_voice_preflight(root, script_candidate, fragment_plan, voice_preflight, payload),
        domain_managed_outputs=True,
    ))
    registry.register(NativeStageAdapter(
        root, execution_stage_id="build-gate4-pre-package",
        implementation_version="gate4-pre-native-v1",
        required_inputs=(script_candidate, material, voice_preflight), declared_outputs=(gate4_pre,),
        execute_fn=lambda: _gate4_pre_package(root, script_candidate, voice_preflight),
    ))
    registry.register(NativeStageAdapter(
        root, execution_stage_id="generate-voice",
        implementation_version="voice-native-v1",
        required_inputs=(approved_script,), declared_outputs=(voice_manifest, duration_report),
        execute_fn=lambda: _generate_voice(root, approved_script, voice_provider, voice_duration),
        domain_managed_outputs=True,
    ))
    registry.register(NativeStageAdapter(
        root, execution_stage_id="build-reconstruction-timeline",
        implementation_version="timeline-native-v1",
        required_inputs=(approved_script, fragment_plan, voice_manifest),
        declared_outputs=(timeline, captions),
        execute_fn=lambda: _build_timeline(approved_script, fragment_plan, voice_manifest),
    ))
    gate4_post = root / "gate_review_packages" / "gate4_post_generation.json"
    registry.register(NativeStageAdapter(
        root, execution_stage_id="build-gate4-post-package",
        implementation_version="gate4-post-native-v1",
        required_inputs=(timeline, captions, voice_manifest, duration_report), declared_outputs=(gate4_post,),
        execute_fn=lambda: _gate4_post_package(root, timeline, captions, voice_manifest, duration_report),
    ))
    registry.register(NativeStageAdapter(
        root, execution_stage_id="summarize-gate4",
        implementation_version="gate4-summary-native-v1",
        required_inputs=(state,), declared_outputs=(),
        execute_fn=lambda: {"status": "approved" if _gates(root).get("gate4") == "approved" else "awaiting_user"},
    ))
    proxy_report = root / "proxy_render_report.json"
    registry.register(NativeStageAdapter(
        root, execution_stage_id="render-proxy",
        implementation_version="proxy-native-v1",
        required_inputs=(timeline,), declared_outputs=(proxy_report,),
        execute_fn=lambda: _render_proxy(root, timeline, proxy_renderer),
    ))
    boundary_report = root / "proxy_boundary_report.json"
    registry.register(NativeStageAdapter(
        root, execution_stage_id="validate-proxy-boundaries",
        implementation_version="proxy-boundary-native-v1",
        required_inputs=(timeline, proxy_report), declared_outputs=(boundary_report,),
        execute_fn=lambda: _validate_boundaries(root, timeline, boundary_frame_times),
    ))
    final_outputs = (
        root / "remix.mp4", captions, root / "final_validation_report.json",
        root / "render_report.json", root / "jianying_import_manifest.json",
    )
    registry.register(NativeStageAdapter(
        root, execution_stage_id="render-final",
        implementation_version="render-final-native-v1",
        required_inputs=(timeline, material, captions), declared_outputs=final_outputs,
        execute_fn=lambda: _render_final(root, final_renderer, media_probe),
        domain_managed_outputs=True,
    ))
    gate5 = root / "gate_review_packages" / "gate5.json"
    registry.register(NativeStageAdapter(
        root, execution_stage_id="build-gate5-package",
        implementation_version="gate5-native-v1",
        required_inputs=final_outputs, declared_outputs=(gate5,),
        execute_fn=lambda: RenderAdapter(
            TaskStorage(root), renderer=final_renderer, media_probe=media_probe
        ).build_gate5_package(created_at=_now(), state_override=_state(root)),
    ))
    destination = Path(archive_root or root / "final") / "remix.mp4"
    registry.register(NativeStageAdapter(
        root, execution_stage_id="archive-approved",
        implementation_version="archive-native-v1",
        required_inputs=(root / "remix.mp4",), declared_outputs=(destination,),
        execute_fn=lambda: _archive(root, archive_root or root / "final"),
        domain_managed_outputs=True,
    ))
    return registry


def _selection_package(root: Path, matches: Path, candidate: Path, payload: Mapping[str, object]) -> Mapping[str, object]:
    decisions = payload.get("overlay_decisions")
    if not isinstance(decisions, Mapping):
        raise ValueError("overlay_decisions are required")
    matches_value = read_json_object(matches)
    candidate_overrides = payload.get("candidate_overrides", {})
    if not isinstance(candidate_overrides, Mapping):
        raise ValueError("candidate_overrides must be an object")
    if candidate_overrides:
        matches_value = copy.deepcopy(matches_value)
        rows = matches_value.get("fragments")
        if not isinstance(rows, list):
            raise ValueError("matches fragments are required")
        for fragment_id, raw_override in candidate_overrides.items():
            if not isinstance(fragment_id, str) or not isinstance(raw_override, Mapping):
                raise ValueError("candidate override is invalid")
            target = next((row for row in rows if isinstance(row, dict) and row.get("fragment_id") == fragment_id), None)
            if target is None:
                raise ValueError(f"candidate override fragment is unknown: {fragment_id}")
            requested_id = raw_override.get("candidate_id")
            requested_hash = raw_override.get("source_sha256")
            candidates = target.get("candidates")
            if not isinstance(candidates, list):
                raise ValueError(f"candidate list is missing: {fragment_id}")
            selected = next((item for item in candidates if isinstance(item, Mapping)
                and item.get("candidate_id", item.get("asset_id")) == requested_id
                and item.get("source_sha256", item.get("sha256")) == requested_hash), None)
            if selected is None:
                raise ValueError(f"candidate override is not allowlisted: {fragment_id}")
            target["selected_asset_id"] = selected.get("asset_id", selected.get("candidate_id"))
    value = RetrievalAdapter().build_candidate_review_package(
        matches=matches_value, overlay_decisions={str(k): str(v) for k, v in decisions.items()}
    )
    range_overrides = payload.get("range_overrides", {})
    if not isinstance(range_overrides, Mapping):
        raise ValueError("range_overrides must be an object")
    selections = value.get("selections")
    if not isinstance(selections, list):
        raise ValueError("material selections are required")
    for fragment_id, raw_range in range_overrides.items():
        if not isinstance(fragment_id, str) or not isinstance(raw_range, Mapping):
            raise ValueError("range override is invalid")
        selection = next((row for row in selections if isinstance(row, dict) and row.get("fragment_id") == fragment_id), None)
        if selection is None:
            raise ValueError(f"range override fragment is unknown: {fragment_id}")
        start = raw_range.get("start_seconds")
        end = raw_range.get("end_seconds")
        available = selection.get("available_source_range")
        if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int, float))
                or not isinstance(end, (int, float)) or not float(start) < float(end)
                or not isinstance(available, Mapping)
                or not isinstance(available.get("start_seconds"), (int, float))
                or not isinstance(available.get("end_seconds"), (int, float))
                or float(start) < float(available["start_seconds"])
                or float(end) > float(available["end_seconds"])):
            raise ValueError(f"range override exceeds available source: {fragment_id}")
        selection["approved_broad_range"] = {"start_seconds": float(start), "end_seconds": float(end)}
    atomic_write_json(candidate, value)
    package = Gate3Adapter().build_material_selection_package(
        candidate_path=candidate, run_id=_state(root)["run_id"],
        state_revision=int(_state(root)["state_revision"]), created_at=_now()
    )
    return {"material_selection_candidate": value, "gate3_material_selection": package}


def _freeze_plan(root: Path, candidate: Path) -> Mapping[str, object]:
    return Gate3Adapter().freeze_fragment_plan(candidate_path=candidate, approval_record=_decision(root, "gate3_material_selection"))


def _evidence_package(root: Path, baseline: Path, plan: Path, output: Path, payload: Mapping[str, object]) -> Mapping[str, object]:
    rows = payload.get("evidence_rows")
    if not isinstance(rows, list):
        raise ValueError("evidence_rows are required")
    matrix = Gate3Adapter().validate_script_evidence(
        content_baseline_path=baseline, fragment_plan_path=plan,
        evidence_rows=[row for row in rows if isinstance(row, Mapping)]
    )
    atomic_write_json(output, matrix)
    package = Gate3Adapter().build_evidence_package(
        evidence_matrix_path=output, run_id=_state(root)["run_id"],
        state_revision=int(_state(root)["state_revision"]), created_at=_now()
    )
    return {"script_evidence_matrix": matrix, "gate3_evidence_closure": package}


def _compile_script(root: Path, baseline: Path, mutation: Path, evidence: Path, narrative: Path) -> Mapping[str, object]:
    source = read_json_object(baseline)
    legacy_task = source.get("narrative_contract_version") != NARRATIVE_CONTRACT_VERSION
    return ProductionScriptCompiler().compile(
        content_baseline_path=baseline, mutation_plan_path=mutation,
        evidence_matrix_path=evidence, evidence_approval_record=_decision(root, "gate3_evidence_closure"),
        narrative_report_path=None if legacy_task else narrative,
    )


def _run_narrative_coherence(
    root: Path, baseline: Path, mutation: Path, blueprint: Path, evidence: Path, output: Path
) -> Mapping[str, object]:
    report = NarrativeCoherenceBuilder().build(
        content_baseline_path=baseline, mutation_plan_path=mutation,
        shot_blueprint_path=blueprint, evidence_matrix_path=evidence,
    )
    atomic_write_json(output, report)
    validation = ArtifactValidator(root).validate_quality_report(output)
    if not validation.valid:
        raise StorageError("narrative report is invalid: " + "; ".join(validation.errors))
    if report["status"] == "passed":
        return {"narrative_status": "passed"}
    state = _state(root)
    return {
        "narrative_status": report["status"],
        "state_changes": {
            "gate_status": {
                **dict(state.get("gate_status", {})),
                "gate4_pre_generation": "blocked",
            },
            "blockers": [
                *list(state.get("blockers", [])),
                {
                    "category": "narrative_coherence_blocked",
                    "stage_id": "build-narrative-coherence",
                    "fragment_ids": report["blocked_fragment_ids"],
                    "allowed_resolutions": report["allowed_resolutions"],
                },
            ],
        },
    }


def _run_visual_layout(
    root: Path, plan: Path, profiles: Path, manifest: Path, output: Path
) -> Mapping[str, object]:
    report = VisualLayoutBuilder().build(
        fragment_plan_path=plan, asset_profiles_path=profiles, material_manifest_path=manifest,
    )
    atomic_write_json(output, report)
    validation = ArtifactValidator(root).validate_quality_report(output)
    if not validation.valid:
        raise StorageError("visual layout report is invalid: " + "; ".join(validation.errors))
    if report["status"] != "blocked":
        return {"layout_status": report["status"]}
    state = _state(root)
    return {
        "layout_status": "blocked",
        "state_changes": {
            "gate_status": {
                **dict(state.get("gate_status", {})),
                "gate4_pre_generation": "blocked",
            },
            "blockers": [
                *list(state.get("blockers", [])),
                {
                    "category": "visual_layout_blocked",
                    "stage_id": "validate-visual-layout",
                    "fragment_ids": report["blocked_fragment_ids"],
                    "allowed_resolutions": report["allowed_resolutions"],
                },
            ],
        },
    }


def _run_voice_preflight(
    root: Path, candidate: Path, plan: Path, output: Path, payload: Mapping[str, object]
) -> Mapping[str, object]:
    speed = payload.get("speed", 1.0)
    if isinstance(speed, bool) or not isinstance(speed, (int, float)):
        raise ValueError("voice preflight speed is invalid")
    report = VoicePreflight().build(
        production_script=read_json_object(candidate),
        fragment_plan=read_json_object(plan),
        speed=float(speed),
    )
    report["requested_tts_settings"] = {
        key: payload[key] for key in ("provider", "speaker", "speed") if key in payload
    }
    report["input_hashes"] = {
        candidate.name: _sha256(candidate),
        plan.name: _sha256(plan),
    }
    atomic_write_json(output, report)
    if report["preflight_status"] != "blocked":
        return {"preflight_status": "passed"}
    state = _state(root)
    return {
        "preflight_status": "blocked",
        "state_changes": {
            "gate_status": {
                **dict(state.get("gate_status", {})),
                "gate4_pre_generation": "blocked",
            },
            "blockers": [
                *list(state.get("blockers", [])),
                {
                    "category": "voice_preflight_failed",
                    "stage_id": "voice-preflight",
                    "fragment_ids": report["blocked_fragment_ids"],
                    "allowed_resolutions": report["allowed_resolutions"],
                },
            ],
        },
    }


def _gate4_pre_package(
    root: Path, candidate: Path, preflight: Path
) -> Mapping[str, object]:
    report = read_json_object(preflight)
    if report.get("preflight_status") != "passed":
        raise ValueError("voice preflight must pass before Gate 4 generation approval")
    return _package(
        root,
        "gate4_pre_generation",
        {
            candidate.name: _sha256(candidate),
            preflight.name: _sha256(preflight),
        },
    )


def _generate_voice(root: Path, script: Path, provider: VoiceProvider, duration: Callable[[Path], float]) -> Mapping[str, object]:
    output = root / "voice"
    generator = VoiceGenerator(provider, sleep=lambda _: None, audio_validator=lambda data: bool(data))
    manifest = generator.generate(script, output)
    segments = []
    for row in manifest.get("segments", []):
        if isinstance(row, Mapping):
            segments.append({**row, "measured_duration_seconds": float(duration(output / str(row["path"])))})
    manifest = {
        "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1", "skill_version": "2.0.0-alpha.1",
        **manifest, "segments": segments,
    }
    atomic_write_json(output / "voice_manifest.json", manifest)
    preflight = read_json_object(root / "voice_preflight.json")
    estimates = {
        str(row.get("fragment_id")): row
        for row in preflight.get("fragments", [])
        if isinstance(row, Mapping) and isinstance(row.get("fragment_id"), str)
    }
    duration_rows = []
    for row in segments:
        estimate = estimates.get(str(row["fragment_id"]), {})
        actual = float(row["measured_duration_seconds"])
        estimated = estimate.get("voice_duration_estimate_seconds")
        duration_rows.append({
            "fragment_id": row["fragment_id"],
            "actual_duration_seconds": actual,
            "estimated_duration_seconds": estimated,
            "delta_vs_estimate_seconds": (
                round(actual - float(estimated), 3) if isinstance(estimated, (int, float)) else None
            ),
            "visual_duration_budget_seconds": estimate.get("visual_duration_budget_seconds"),
        })
    atomic_write_json(output / "duration_report.json", {
        "artifact_type": "duration_report",
        "schema_id": "urn:capcut:remix-reference-video:artifact:duration-report",
        "schema_version": "1.0.0",
        "contract_version": "2.0.0-alpha.1",
        "skill_version": "2.0.0-alpha.1",
        "source_voice_manifest_sha256": _sha256(output / "voice_manifest.json"),
        "fragments": duration_rows,
        "total_duration_seconds": round(sum(row["actual_duration_seconds"] for row in duration_rows), 3),
    })
    return manifest


def _build_timeline(script: Path, plan: Path, voice: Path) -> Mapping[str, object]:
    result = TimelineBuilder().build(
        approved_script=read_json_object(script), fragment_plan=read_json_object(plan), voice_manifest=read_json_object(voice)
    )
    return {"reconstruction_timeline": result["timeline"], "captions_srt": result["captions_srt"]}


def _gate4_post_package(
    root: Path, timeline: Path, captions: Path, voice: Path, duration_report: Path
) -> Mapping[str, object]:
    return _package(
        root,
        "gate4_post_generation",
        {
            path.relative_to(root).as_posix(): _sha256(path)
            for path in (timeline, captions, voice, duration_report)
        },
    )


def _render_proxy(root: Path, timeline: Path, renderer: Callable[..., Mapping[str, object]]) -> Mapping[str, object]:
    result = ReconstructionAdapter(root, root).render_proxy(
        timeline=read_json_object(timeline), gate_status=_gates(root), task_config={}, renderer=renderer
    )
    return {"artifact_type": "proxy_render_report", **dict(result)}


def _validate_boundaries(root: Path, timeline: Path, frame_times: Callable[[Path], Sequence[float]]) -> Mapping[str, object]:
    return ReconstructionAdapter.validate_proxy_boundaries(
        timeline=read_json_object(timeline), observed_frame_times=frame_times(root / "proxy.mp4"), fps=30
    )


def _render_final(root: Path, renderer: Callable[..., Mapping[str, object]], probe: Callable[[Path], Mapping[str, object]]) -> Mapping[str, object]:
    RenderAdapter(TaskStorage(root), renderer=renderer, media_probe=probe).render_final(
        manage_state=False, state_override=_state(root)
    )
    state = _state(root)
    return {
        "status": "rendered",
        "state_changes": {
            "gate_status": {**dict(state.get("gate_status", {})), "gate5": "awaiting_user"},
            "stages": {
                **dict(state.get("stages", {})),
                "render": {"status": "awaiting_user"},
                "final_review": {"status": "awaiting_user"},
            },
            "active_stage": "final_review",
        },
    }


def _archive(root: Path, final_root: Path) -> Mapping[str, object]:
    path = RenderAdapter(TaskStorage(root), renderer=lambda **_: {}, media_probe=lambda _: {}).archive_approved(
        final_root=final_root, output_name="remix.mp4", state_override=_state(root)
    )
    return {"path": str(path)}


def _package(root: Path, gate_id: str, hashes: Mapping[str, str]) -> Mapping[str, object]:
    return {
        "artifact_type": "gate_review_package", "schema_id": "urn:capcut:remix-reference-video:artifact:gate-review-package",
        "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1", "skill_version": "2.0.0-alpha.1",
        "gate_id": gate_id, "run_id": _state(root)["run_id"], "state_revision": _state(root)["state_revision"],
        "created_at": _now(), "input_hashes": dict(hashes),
    }


def _state(root: Path) -> dict[str, object]:
    return read_json_object(root / "pipeline_state.json")


def _gates(root: Path) -> Mapping[str, object]:
    gates = _state(root).get("gate_status")
    return gates if isinstance(gates, Mapping) else {}


def _decision(root: Path, gate_id: str) -> Mapping[str, object]:
    for record in reversed(_state(root).get("decisions", [])):
        if isinstance(record, Mapping) and record.get("gate_id") == gate_id and record.get("decision") == "approved":
            return record
    raise ValueError(f"approved decision is required: {gate_id}")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


__all__ = ["register_completion_adapters"]
