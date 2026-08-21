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
from .adapters.script_candidates import ScriptCandidateGenerator, ScriptCandidateValidator
from .adapters.shot_quality import ShotQualityAdapter
from .adapters.final_diagnostic import FinalContentDiagnosticAdapter
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
    script_candidate_provider: str | None = None,
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
    script_candidates = root / "script_candidates.json"
    script_candidate_validation = root / "script_candidate_validation_report.json"
    creative_objective = root / "creative_objective.json"
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
    if _creative_run(root):
        registry.register(NativeStageAdapter(
            root, execution_stage_id="generate-script-candidates",
            implementation_version="script-candidates-native-v1",
            required_inputs=(evidence, narrative_report, baseline, creative_objective, fragment_plan), declared_outputs=(script_candidates,),
            execute_fn=lambda: _generate_script_candidates(
                evidence, narrative_report, baseline, creative_objective, fragment_plan,
                script_candidate_provider,
            ),
        ))
        registry.register(NativeStageAdapter(
            root, execution_stage_id="validate-script-candidates",
            implementation_version="script-candidates-validation-native-v1",
            required_inputs=(script_candidates, creative_objective), declared_outputs=(script_candidate_validation,),
            execute_fn=lambda: _validate_script_candidates(script_candidates, creative_objective),
        ))
        registry.register(NativeStageAdapter(
            root, execution_stage_id="select-script-candidate",
            implementation_version="script-candidate-selection-native-v1",
            required_inputs=(script_candidates, script_candidate_validation), declared_outputs=(script_candidate,),
            execute_fn=lambda: _select_script_candidate(script_candidates, script_candidate_validation),
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
        root, execution_stage_id="validate-shot-quality",
        implementation_version="shot-quality-native-v1",
        required_inputs=(timeline, material, proxy_report), declared_outputs=(root / "shot_quality_report.json",),
        execute_fn=lambda: _validate_shot_quality(root, timeline, material, proxy_report),
        domain_managed_outputs=True,
    ))
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
    diagnostic = root / "final_content_diagnostic_report.json"
    registry.register(NativeStageAdapter(
        root, execution_stage_id="build-final-content-diagnostic",
        implementation_version="final-diagnostic-native-v1",
        required_inputs=(root / "shot_quality_report.json", creative_objective), declared_outputs=(diagnostic,),
        execute_fn=lambda: _build_final_diagnostic(root / "shot_quality_report.json", creative_objective, diagnostic),
        domain_managed_outputs=True,
    ))
    registry.register(NativeStageAdapter(
        root, execution_stage_id="build-gate5-package",
        implementation_version="gate5-native-v1",
        required_inputs=(*final_outputs, diagnostic) if _creative_run(root) else final_outputs, declared_outputs=(gate5,),
        execute_fn=lambda: _build_gate5_package(root, final_renderer, media_probe, diagnostic),
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
    if _creative_run(root):
        selected = root / "production_script_candidate.json"
        validation = root / "script_candidate_validation_report.json"
        selected_id = _selected_script_candidate(root, selected)
        if selected_id is None or not validation.is_file():
            raise ValueError("creative script candidate selection is required")
        passed = {
            str(row.get("script_candidate_id"))
            for row in read_json_object(validation).get("candidates", [])
            if isinstance(row, Mapping) and row.get("status") == "passed"
        }
        if selected_id not in passed:
            raise ValueError("selected creative script candidate is not passed")
        return read_json_object(selected)
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
    hashes = {
        candidate.name: _sha256(candidate),
        preflight.name: _sha256(preflight),
    }
    bindings: dict[str, object] = {}
    if _creative_run(root):
        for name in ("script_candidates.json", "script_candidate_validation_report.json"):
            path = root / name
            if path.is_file() and not path.is_symlink():
                hashes[name] = _sha256(path)
        selected = _selected_script_candidate(root, candidate)
        if selected is not None:
            bindings["selected_script_candidate_id"] = selected
            bindings["script_candidate_validation_report.json_sha256"] = hashes.get(
                "script_candidate_validation_report.json"
            )
    return _package(
        root,
        "gate4_pre_generation",
        hashes,
        **({"creative_bindings": bindings} if bindings else {}),
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


def _generate_script_candidates(
    evidence: Path,
    narrative: Path,
    baseline: Path,
    objective: Path,
    fragment_plan: Path,
    provider: str | None,
) -> Mapping[str, object]:
    evidence_value = read_json_object(evidence)
    narrative_value = read_json_object(narrative)
    baseline_value = read_json_object(baseline)
    plan_value = read_json_object(fragment_plan)
    baseline_rows = {
        str(row.get("fragment_id")): row
        for row in baseline_value.get("fragments", [])
        if isinstance(row, Mapping) and isinstance(row.get("fragment_id"), str)
    }
    plans = {
        str(row.get("fragment_id")): row
        for row in plan_value.get("fragments", [])
        if isinstance(row, Mapping) and isinstance(row.get("fragment_id"), str)
    }
    fragments = []
    for row in evidence_value.get("rows", []):
        if isinstance(row, Mapping):
            narrative_row = next((item for item in narrative_value.get("fragments", []) if isinstance(item, Mapping) and item.get("fragment_id") == row.get("fragment_id")), {})
            fragment_id = str(row.get("fragment_id"))
            source = baseline_rows.get(fragment_id, {})
            plan = plans.get(fragment_id, {})
            broad = plan.get("approved_broad_range")
            budget = (
                float(broad["end_seconds"]) - float(broad["start_seconds"])
                if isinstance(broad, Mapping)
                and isinstance(broad.get("start_seconds"), (int, float))
                and isinstance(broad.get("end_seconds"), (int, float))
                else None
            )
            fragments.append({
                **dict(source), **dict(row), **dict(narrative_row),
                "evidence_row_ref": str(row.get("evidence_row_ref") or f"evidence:{fragment_id}"),
                "visual_duration_budget_seconds": budget,
            })
    return ScriptCandidateGenerator(provider=provider, seed=0).generate({
        "objective": read_json_object(objective),
        "evidence": {"fragments": fragments},
    })


def _validate_script_candidates(path: Path, objective: Path) -> Mapping[str, object]:
    value = read_json_object(path)
    return ScriptCandidateValidator().validate(value, {"objective": read_json_object(objective)})


def _select_script_candidate(candidates_path: Path, validation_path: Path) -> Mapping[str, object]:
    candidates = read_json_object(candidates_path)
    validation = read_json_object(validation_path)
    selected = ScriptCandidateValidator().select(candidates, validation)
    lines = []
    for row in selected.get("lines", []):
        if not isinstance(row, Mapping):
            raise ValueError("selected script line is invalid")
        lines.append({**dict(row), "line_id": row["script_line_id"]})
    return {
        "artifact_type": "production_script_candidate",
        "schema_id": "urn:capcut:remix-reference-video:artifact:production-script-candidate",
        "schema_version": "1.0.0",
        "contract_version": "2.0.0-alpha.1",
        "skill_version": "2.0.0-alpha.1",
        "lifecycle_status": "awaiting_user",
        "selected_script_candidate_id": selected["script_candidate_id"],
        "selection_policy_version": "script_candidate_rank_v1",
        "input_hashes": {
            "script_candidates.json": _sha256(candidates_path),
            "script_candidate_validation_report.json": _sha256(validation_path),
        },
        "lines": lines,
    }


def _validate_shot_quality(root: Path, timeline: Path, material: Path, proxy: Path) -> Mapping[str, object]:
    report = ShotQualityAdapter().build(script=read_json_object(root / "production_script_candidate.json"), timeline=read_json_object(timeline), material=read_json_object(material), proxy=read_json_object(proxy))
    atomic_write_json(root / "shot_quality_report.json", report)
    if report["status"] != "blocked":
        return {"status": "succeeded", "shot_quality_status": report["status"]}
    blocked = [str(row.get("shot_id")) for row in report.get("shots", []) if isinstance(row, Mapping) and row.get("status") == "blocked"]
    return {
        "status": "recoverable_pause",
        "active_stage": "validate-shot-quality",
        "blocker": {
            "category": "shot_quality_blocked", "requires_user": True,
            "detail": "分镜存在缺失动作、素材或时间线问题，不能进入正式渲染。",
            "shot_ids": blocked,
        },
        "next_actions": ["request_change:gate3_material_selection", "request_change:gate4_pre_generation"],
    }


def _build_final_diagnostic(shot_quality: Path, objective: Path, output: Path) -> Mapping[str, object]:
    report = FinalContentDiagnosticAdapter().build(
        shot_quality=read_json_object(shot_quality), objective=read_json_object(objective)
    )
    atomic_write_json(output, report)
    if report["status"] != "blocked":
        return {"status": "succeeded", "final_diagnostic_status": report["status"]}
    return {
        "status": "recoverable_pause",
        "active_stage": "build-final-content-diagnostic",
        "blocker": {
            "category": "final_content_diagnostic_blocked", "requires_user": True,
            "detail": "成片未满足已批准的必达目标，不能进入 Gate 5 审核。",
            "blocked_check_ids": report.get("blocked_check_ids", []),
        },
        "next_actions": ["request_change:gate4_pre_generation", "request_change:gate3_material_selection"],
    }


def _build_gate5_package(
    root: Path,
    renderer: Callable[..., Mapping[str, object]],
    probe: Callable[[Path], Mapping[str, object]],
    diagnostic: Path,
) -> Mapping[str, object]:
    package = RenderAdapter(TaskStorage(root), renderer=renderer, media_probe=probe).build_gate5_package(
        created_at=_now(), state_override=_state(root)
    )
    if _creative_run(root):
        if not diagnostic.is_file() or diagnostic.is_symlink():
            raise ValueError("creative Gate 5 requires final content diagnostic")
        return {**package, "input_hashes": {**dict(package["input_hashes"]), diagnostic.name: _sha256(diagnostic)}}
    return package


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


def _package(
    root: Path,
    gate_id: str,
    hashes: Mapping[str, str],
    **extra: object,
) -> Mapping[str, object]:
    return {
        "artifact_type": "gate_review_package", "schema_id": "urn:capcut:remix-reference-video:artifact:gate-review-package",
        "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1", "skill_version": "2.0.0-alpha.1",
        "gate_id": gate_id, "run_id": _state(root)["run_id"], "state_revision": _state(root)["state_revision"],
        "created_at": _now(), "input_hashes": dict(hashes), **extra,
    }


def _creative_run(root: Path) -> bool:
    snapshot = root / "g_b_frozen_input_snapshot.json"
    if not snapshot.is_file() or snapshot.is_symlink():
        return False
    try:
        return read_json_object(snapshot).get("creative_contract_version") == "creative_contract_v1"
    except (OSError, StorageError, TypeError, ValueError):
        return False


def _selected_script_candidate(root: Path, candidate: Path) -> str | None:
    try:
        value = read_json_object(candidate)
    except (OSError, StorageError, TypeError, ValueError):
        return None
    for key in ("selected_script_candidate_id", "script_candidate_id"):
        selected = value.get(key)
        if isinstance(selected, str) and selected:
            return selected
    return None


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
