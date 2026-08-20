"""Deterministic business-facing workspace projection over canonical run artifacts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .snapshot_schema_validator import SnapshotSchemaValidator
from .storage import StorageError, read_json_object, read_jsonl_records


class WorkspaceViewError(StorageError):
    """Raised when a workspace projection cannot be built safely."""


_BUSINESS_STAGES = (
    ("参考拆解", ("gate1",)),
    ("复刻方案", ("gate2",)),
    ("素材与证据", ("gate3_material_selection", "gate3_evidence_closure")),
    ("文案与声音", ("gate4_pre_generation", "gate4_post_generation")),
    ("成片终审", ("gate5",)),
)
_GATE_TO_STAGE = {gate: (label, index) for index, (label, gates) in enumerate(_BUSINESS_STAGES) for gate in gates}
_GATE_QUESTIONS = {
    "gate1": "镜头顺序、节奏和关键镜头是否可接受？",
    "gate2": "内容基线与结构变化是否可接受？",
    "gate3_material_selection": "每段配的素材画面是否可用？",
    "gate3_evidence_closure": "每句口播是否都有对应画面证据？",
    "gate4_pre_generation": "生产文案、音色和语速是否批准？",
    "gate4_post_generation": "逐句配音、字幕边界和停顿是否可用？",
    "gate5": "最终预览、质量结果和交付文件是否通过？",
}
_ARTIFACT_FILES = (
    "project_brief.json", "recipe.json", "shot_blueprint.json", "content_baseline.json", "mutation_plan.json",
    "coverage_report.json", "matches.json", "fragment_plan.json", "script_evidence_matrix.json",
    "production_script_candidate.json", "approved_production_script.json", "voice_preflight.json",
    "reconstruction_timeline.json", "final_validation_report.json", "render_report.json", "captions.srt",
    "voice/voice_manifest.json", "voice/voice_qa_report.json", "remix.mp4",
    "decomposition_bundle.json", "creative_objective.json", "remix_strategy_candidates.json",
    "script_candidates.json", "script_candidate_validation_report.json", "shot_quality_report.json",
    "final_content_diagnostic_report.json", "enhancement_plan.json",
)
_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
_VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm")
_AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac")
_BUSINESS_ARTIFACTS = {
    "recipe.json": ("参考拆解", "参考事实层"),
    "shot_blueprint.json": ("复刻方案", "分镜方案"),
    "content_baseline.json": ("复刻方案", "内容基线"),
    "mutation_plan.json": ("复刻方案", "变化范围"),
    "coverage_report.json": ("复刻方案", "覆盖报告"),
    "matches.json": ("素材与证据", "素材匹配"),
    "fragment_plan.json": ("素材与证据", "已选素材范围"),
    "script_evidence_matrix.json": ("素材与证据", "口播证据闭环"),
    "material_manifest.json": ("文案与声音", "素材物化清单"),
    "narrative_coherence_report.json": ("文案与声音", "叙事连贯性报告"),
    "visual_layout_report.json": ("文案与声音", "图片布局报告"),
    "voice_preflight.json": ("文案与声音", "声音预算检查"),
    "production_script_candidate.json": ("文案与声音", "生产文案候选"),
    "approved_production_script.json": ("文案与声音", "已批准生产文案"),
    "voice/voice_manifest.json": ("文案与声音", "生成语音"),
    "reconstruction_timeline.json": ("文案与声音", "真实剪辑时间线"),
    "final_validation_report.json": ("成片终审", "成片技术校验"),
    "render_report.json": ("成片终审", "渲染结果"),
    "remix.mp4": ("成片终审", "最终成片"),
    "captions.srt": ("成片终审", "字幕"),
    "jianying_import_manifest.json": ("成片终审", "剪映导入清单"),
    "decomposition_bundle.json": ("参考拆解", "拆解策略候选"),
    "creative_objective.json": ("复刻方案", "创作目标"),
    "remix_strategy_candidates.json": ("复刻方案", "复刻策略候选"),
    "script_candidates.json": ("文案与声音", "脚本候选"),
    "script_candidate_validation_report.json": ("文案与声音", "脚本候选校验"),
    "shot_quality_report.json": ("成片终审", "分镜质量诊断"),
    "final_content_diagnostic_report.json": ("成片终审", "成片内容诊断"),
    "enhancement_plan.json": ("素材与证据", "增强候选计划"),
}
_STAGE_BUSINESS = {
    "split-reference": "参考拆解",
    "index-assets": "素材索引",
    "build-coverage-precheck": "复刻方案",
    "compile-blueprint": "复刻方案",
    "compile-mutation-plan": "复刻方案",
    "lint-gate2-package": "复刻方案",
    "build-material-evidence-requirements": "素材证据补充",
    "build-coverage-authoritative": "复刻方案",
    "match-assets": "素材与证据",
    "build-material-selection-package": "素材与证据",
    "freeze-fragment-plan": "素材与证据",
    "validate-script-evidence": "素材与证据",
    "summarize-gate3": "素材与证据",
    "build-narrative-coherence": "文案与声音",
    "build-production-script": "文案与声音",
    "materialize-approved-broad": "文案与声音",
    "validate-visual-layout": "文案与声音",
    "voice-preflight": "文案与声音",
    "build-gate4-pre-package": "文案与声音",
    "generate-voice": "文案与声音",
    "build-reconstruction-timeline": "文案与声音",
    "build-gate4-post-package": "文案与声音",
    "summarize-gate4": "文案与声音",
    "render-proxy": "成片终审",
    "validate-proxy-boundaries": "成片终审",
    "render-final": "成片终审",
    "build-gate5-package": "成片终审",
    "archive-approved": "成片终审",
}
_MATERIAL_GATES = {"gate3_material_selection", "gate3_evidence_closure", "gate4_pre_generation", "gate4_post_generation", "gate5"}
_EVIDENCE_GATES = {"gate3_evidence_closure", "gate4_pre_generation", "gate4_post_generation", "gate5"}
_VOICE_GATES = {"gate4_pre_generation", "gate4_post_generation", "gate5"}
_RISK_STATUSES = {"blocked", "rejected", "stale"}


class WorkbenchWorkspaceBuilder:
    def __init__(self, task_root: Path) -> None:
        root = Path(task_root)
        if root.is_symlink():
            raise WorkspaceViewError("task root must not be a symlink")
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise WorkspaceViewError("task root must be a directory")
        self.validator = SnapshotSchemaValidator()

    def build(self, gate_id: str) -> dict[str, Any]:
        if gate_id not in _GATE_TO_STAGE:
            raise WorkspaceViewError(f"unsupported Gate: {gate_id}")
        state = read_json_object(self.root / "pipeline_state.json")
        label, stage_index = _GATE_TO_STAGE[gate_id]
        brief = self._optional_json("project_brief.json")
        recipe = self._optional_json("recipe.json")
        blueprint = self._optional_json("shot_blueprint.json")
        baseline = self._optional_json("content_baseline.json")
        mutation = self._optional_json("mutation_plan.json")
        matches = self._optional_json("matches.json")
        fragment_plan = self._optional_json("fragment_plan.json")
        evidence_matrix = self._optional_json("script_evidence_matrix.json")
        voice_manifest = self._optional_json("voice/voice_manifest.json")
        approved_script = self._optional_json("approved_production_script.json")
        script_candidate = self._optional_json("production_script_candidate.json")
        script_candidates = self._optional_json("script_candidates.json")
        script_candidate_validation = self._optional_json("script_candidate_validation_report.json")
        decomposition = self._optional_json("decomposition_bundle.json")
        material_evidence = self._optional_json("material_evidence_requirements.json")
        preflight = self._optional_json("voice_preflight.json")
        reconstruction = self._optional_json("reconstruction_timeline.json")
        final_validation = self._optional_json("final_validation_report.json")
        render_report = self._optional_json("render_report.json")
        storyboard = self._storyboard(
            recipe,
            blueprint if gate_id != "gate1" else None,
            baseline if gate_id != "gate1" else None,
            matches if gate_id in _MATERIAL_GATES else None,
            fragment_plan if gate_id in _MATERIAL_GATES else None,
            evidence_matrix if gate_id in _EVIDENCE_GATES else None,
            voice_manifest if gate_id in _VOICE_GATES else None,
            state,
        )
        storyboard["section_states"] = self._section_states(gate_id, storyboard)
        timeline = self._timeline(gate_id, recipe, fragment_plan, reconstruction, final_validation, render_report, storyboard)
        media_allowlist = self._media_allowlist(gate_id, storyboard, timeline, brief, recipe)
        required = self._required_files(gate_id)
        missing = [name for name in required if not self._exists(name)]
        blockers = [item for item in state.get("blockers", []) if isinstance(item, Mapping) and item.get("requires_user", True)]
        gate_status = str(state.get("gate_status", {}).get(gate_id, "not_ready"))
        lifecycle = "stale" if gate_status in _RISK_STATUSES and not (missing or blockers) else ("not_ready" if missing or blockers or gate_status == "not_ready" else "ready")
        task = self._text(brief, ("task_name", "name", "title")) or self._nested_text(brief, "project", ("title", "name", "slug")) or "待确认"
        product = self._text(brief, ("product_name", "product_label")) or self._nested_text(brief, "product", ("name", "label")) or "待确认"
        platform = self._text(brief, ("platform", "target_platform")) or self._nested_text(brief, "target", ("platform",)) or "待确认"
        progress = round((stage_index + (1 if lifecycle == "ready" else 0)) / len(_BUSINESS_STAGES), 2)
        statuses = state.get("gate_status") if isinstance(state.get("gate_status"), Mapping) else {}
        stages = []
        for business_label, gates in _BUSINESS_STAGES:
            gate_rows = [{"gate_id": gate, "status": str(statuses.get(gate, "not_ready"))} for gate in gates]
            stage_status = self._aggregate_stage_status(gate_rows)
            stages.append({"stage_id": f"stage{len(stages) + 1}", "business_label": business_label, "gate_ids": list(gates), "status": stage_status, "substeps": gate_rows})
        evidence = self._decision_evidence(gate_id, missing, recipe, baseline, mutation, matches, fragment_plan, evidence_matrix, preflight, reconstruction, final_validation, render_report)
        if gate_status == "rejected":
            recommendation = "当前审核已驳回，请按修改范围重新生成审核包。"
        elif gate_status == "blocked":
            recommendation = "当前审核被阻塞，请先处理阻塞项。"
        elif gate_status == "stale":
            recommendation = "当前审核包已过期，请重新确认最新产物。"
        elif missing or blockers:
            recommendation = "待确认：请先补齐缺失事实或处理阻塞。"
        elif gate_status == "awaiting_user":
            recommendation = "建议通过当前已具备的审核内容。"
        else:
            recommendation = "当前 Gate 不在待审核状态。"
        collecting_material_evidence = state.get("active_stage") == "collect-material-evidence"
        process_stage = "素材证据补充" if collecting_material_evidence else label
        view: dict[str, Any] = {
            "artifact_type": "workbench_workspace_view",
            "schema_id": "urn:capcut:remix-reference-video:artifact:workbench-workspace-view",
            "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1", "skill_version": "2.0.0-alpha.1",
            "run_id": str(state.get("run_id", "")), "state_revision": int(state.get("state_revision", 0)),
            "package_revision": state.get("package_revision", state.get("state_revision", 0)),
            "current_gate": gate_id, "lifecycle_status": lifecycle,
            "summary": {
                "task": task, "product": product, "platform": platform, "business_stage": label,
                "current_stage": label, "progress": progress, "connection_ready": True,
                "connection_status": "ready", "version": "待确认" if lifecycle != "ready" else f"r{state.get('state_revision', 0)}",
            },
            "storyboard": storyboard,
            "unclassified_assets": self._unclassified_assets(storyboard, media_allowlist),
            "preview": self._preview(gate_id, recipe, media_allowlist),
            "timeline": timeline,
            "artifacts": self._artifacts(state),
            "quality_checks": self._quality_checks(final_validation, render_report),
            "process": {"current_stage": process_stage, "current_gate": gate_id, "stages": stages, "execution": self._execution()},
            "decision_context": {
                "question": _GATE_QUESTIONS[gate_id], "recommendation": recommendation,
                "evidence": evidence, "risks": [str(item.get("detail") or item.get("category") or "待确认阻塞") for item in blockers],
                "next_action": "补充素材业务证据后继续匹配" if collecting_material_evidence else ("按驳回原因重新生成审核包" if gate_status == "rejected" else ("处理阻塞并重新审核" if gate_status == "blocked" else ("刷新审核包后重新确认" if gate_status == "stale" else ("补齐缺失事实并重新审核" if missing or blockers else "选择通过、要求修改或驳回")))),
                "approval_eligibility": gate_status == "awaiting_user" and not missing and not blockers and lifecycle == "ready",
                "gate_status": gate_status,
                "missing_artifacts": missing,
                "claims": {
                    "approved": [row for row in (baseline or {}).get("claims", []) if isinstance(row, Mapping) and row.get("status", "approved") != "forbidden"] if gate_id == "gate2" else [],
                    "forbidden": list((mutation or {}).get("forbidden_claims", [])) if gate_id == "gate2" and isinstance(mutation, Mapping) else [],
                },
                "structure": list((baseline or {}).get("fragments", [])) if gate_id == "gate2" and isinstance(baseline, Mapping) else [],
                "source_text_treatment": list((matches or {}).get("source_text_treatment", [])) if gate_id in {"gate3_material_selection", "gate3_evidence_closure"} and isinstance(matches, Mapping) else [],
                "evidence_coverage": (evidence_matrix or {}).get("coverage", []) if gate_id == "gate3_evidence_closure" and isinstance(evidence_matrix, Mapping) else [],
                "missing_objects": list((matches or {}).get("missing_objects", [])) if gate_id in {"gate3_material_selection", "gate3_evidence_closure"} and isinstance(matches, Mapping) else [],
                "production_script": self._artifact_summary(gate_id, approved_script or script_candidate, "script"),
                "script_details": self._script_details(gate_id, approved_script, script_candidate),
                "script_candidates": script_candidates.get("candidates", []) if isinstance(script_candidates, Mapping) else [],
                "script_candidate_validation": script_candidate_validation.get("candidates", []) if isinstance(script_candidate_validation, Mapping) else [],
                "decomposition_candidates": decomposition.get("candidates", []) if isinstance(decomposition, Mapping) else [],
                "material_evidence": {
                    "status": material_evidence.get("status"),
                    "requirements": material_evidence.get("requirements", []),
                    "input_hashes": material_evidence.get("input_hashes", {}),
                    "submission_hashes": {
                        "material_evidence_requirements.json": self._file_sha256("material_evidence_requirements.json"),
                        "asset_profiles.json": self._file_sha256("asset_profiles.json") if self._exists("asset_profiles.json") else None,
                    },
                } if collecting_material_evidence and isinstance(material_evidence, Mapping) else None,
                "voice_preflight": self._artifact_summary(gate_id, preflight, "voice_preflight"),
                "voice_preflight_details": self._voice_preflight_details(gate_id, preflight),
                "generated_voice": self._artifact_summary(gate_id, voice_manifest, "voice"),
                "subtitle_boundary_results": self._artifact_summary(gate_id, self._optional_json("voice/voice_qa_report.json"), "subtitle_boundary"),
                "quality": {
                    "l0": (final_validation or {}).get("l0") if isinstance(final_validation, Mapping) else None,
                    "l1": (final_validation or {}).get("l1") if isinstance(final_validation, Mapping) else None,
                    "p": (final_validation or {}).get("p") if isinstance(final_validation, Mapping) else None,
                    "production_audit": (render_report or {}).get("production_audit") if isinstance(render_report, Mapping) else None,
                    "subtitles": self._artifact_summary(gate_id, self._optional_json("captions.srt"), "subtitles"),
                    "render_report": render_report if gate_id == "gate5" else None,
                    "delivery_files": [name for name in ("remix.mp4", "captions.srt", "render_report.json", "jianying_import_manifest.json") if self._exists(name)] if gate_id == "gate5" else [],
                },
            },
            "media_allowlist": media_allowlist,
        }
        view["summary"]["top_bar"] = {key: view["summary"][key] for key in ("task", "product", "platform", "business_stage", "progress", "connection_ready", "connection_status", "version")}
        self.validator.assert_valid(view, "workbench-workspace-view.schema.json")
        return view

    def _optional_json(self, relative: str) -> dict[str, Any] | None:
        path = self.root / relative
        if path.is_symlink() or not path.is_file():
            return None
        try:
            return read_json_object(path)
        except StorageError:
            return None

    def _exists(self, relative: str) -> bool:
        if not isinstance(relative, str) or not relative:
            return False
        path = self.root / relative
        return path.is_file() and not path.is_symlink()

    @staticmethod
    def _text(value: Mapping[str, Any] | None, keys: tuple[str, ...]) -> str | None:
        if not value:
            return None
        for key in keys:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        return None

    @classmethod
    def _nested_text(cls, value: Mapping[str, Any] | None, section: str, keys: tuple[str, ...]) -> str | None:
        nested = value.get(section) if isinstance(value, Mapping) else None
        return cls._text(nested if isinstance(nested, Mapping) else None, keys)

    @staticmethod
    def _media_type(path: str | None) -> str | None:
        if not isinstance(path, str) or not path:
            return None
        lower = path.lower()
        if lower.endswith(_IMAGE_EXT):
            return "image"
        if lower.endswith(_VIDEO_EXT):
            return "video"
        if lower.endswith(_AUDIO_EXT):
            return "audio"
        return None

    @staticmethod
    def _aggregate_stage_status(rows: list[Mapping[str, Any]]) -> str:
        statuses = {str(row.get("status", "not_ready")) for row in rows}
        for status in ("blocked", "rejected", "stale"):
            if status in statuses:
                return status
        if statuses and statuses == {"approved"}:
            return "approved"
        if "awaiting_user" in statuses:
            return "awaiting_user"
        return "not_ready"

    def _storyboard(self, recipe: Mapping[str, Any] | None, blueprint: Mapping[str, Any] | None, baseline: Mapping[str, Any] | None, matches: Mapping[str, Any] | None, plan: Mapping[str, Any] | None, evidence: Mapping[str, Any] | None, voice_manifest: Mapping[str, Any] | None, state: Mapping[str, Any]) -> dict[str, Any]:
        recipe_shots = recipe.get("shots", []) if isinstance(recipe, Mapping) else []
        if not isinstance(recipe_shots, list):
            recipe_shots = []
        fragments = (plan or {}).get("fragments", []) if isinstance(plan, Mapping) else []
        if not isinstance(fragments, list) or not fragments:
            fragments = (blueprint or {}).get("fragments", []) if isinstance(blueprint, Mapping) else []
        if not isinstance(fragments, list):
            fragments = []
        match_rows = {str(row.get("fragment_id")): row for row in (matches or {}).get("fragments", []) if isinstance(row, Mapping) and row.get("fragment_id") is not None}
        baseline_rows = {str(row.get("fragment_id")): row for row in (baseline or {}).get("fragments", []) if isinstance(row, Mapping) and row.get("fragment_id") is not None}
        evidence_rows = (evidence or {}).get("rows", []) if isinstance(evidence, Mapping) else []
        if not isinstance(evidence_rows, list):
            evidence_rows = []
        evidence_by_fragment = {str(row.get("fragment_id")): row for row in evidence_rows if isinstance(row, Mapping) and row.get("fragment_id") is not None}
        claim_fragments: dict[str, list[str]] = {}
        for fragment_id, row in baseline_rows.items():
            for claim_id in row.get("claim_ids", []) or []:
                claim_fragments.setdefault(str(claim_id), []).append(fragment_id)
        for fragment_id, row in evidence_by_fragment.items():
            for claim_id in row.get("approved_claim_ids", []) or []:
                key = str(claim_id)
                if fragment_id not in claim_fragments.get(key, []):
                    claim_fragments.setdefault(key, []).append(fragment_id)
        shots: list[dict[str, Any]] = []
        for index, raw in enumerate(recipe_shots):
            if not isinstance(raw, Mapping):
                continue
            raw_id = str(raw.get("shot_id") or raw.get("id") or index + 1)
            reference_ref = raw.get("clip_path") or raw.get("media_ref") or raw.get("path")
            thumbnail_ref = raw.get("keyframe_path") or reference_ref
            thumbnail_ref = thumbnail_ref if isinstance(thumbnail_ref, str) and self._exists(thumbnail_ref) else None
            reference_ref = reference_ref if isinstance(reference_ref, str) and self._exists(reference_ref) else None
            shots.append({"shot_id": f"shot-{raw_id}", "order": index + 1, "business_label": str(raw.get("label") or raw.get("title") or f"参考分镜 {index + 1}"), "purpose": str(raw.get("purpose") or raw.get("narrative_role") or "参考节奏"), "status": "ready", "media_type": self._media_type(reference_ref) or "video", "thumbnail_ref": thumbnail_ref, "media_ref": reference_ref, "reference_media_ref": reference_ref, "start_seconds": raw.get("start_seconds"), "end_seconds": raw.get("end_seconds")})
        for index, raw in enumerate(fragments):
            if not isinstance(raw, Mapping):
                continue
            fragment_id = str(raw.get("fragment_id") or raw.get("id") or index + 1)
            row = match_rows.get(fragment_id, {})
            candidate = row.get("selected_candidate") if isinstance(row, Mapping) else None
            if not isinstance(candidate, Mapping):
                candidates = row.get("candidates", []) if isinstance(row, Mapping) else []
                selected_id = row.get("selected_asset_id") if isinstance(row, Mapping) else raw.get("asset_id")
                candidate = next((item for item in candidates if isinstance(item, Mapping) and item.get("asset_id") == selected_id), None) if isinstance(candidates, list) else None
                if not isinstance(candidate, Mapping):
                    candidate = candidates[0] if isinstance(candidates, list) and candidates and isinstance(candidates[0], Mapping) else {}
            source_path = raw.get("source_path") or candidate.get("source_path") or candidate.get("path")
            material_path = f"material/{fragment_id}/{Path(str(source_path)).name}" if isinstance(source_path, str) else None
            path = material_path if isinstance(material_path, str) and self._exists(material_path) else None
            frame_path = f"gate3_review_frames/{fragment_id}.jpg"
            frame = frame_path if self._exists(frame_path) else None
            baseline_row = baseline_rows.get(fragment_id, {})
            label = raw.get("label") or raw.get("title") or baseline_row.get("label") or f"生产分镜 {index + 1}"
            purpose = raw.get("narration") or raw.get("purpose") or baseline_row.get("narration") or baseline_row.get("intent") or "产品展示"
            media_type = candidate.get("media_type") if isinstance(candidate, Mapping) else None
            if not isinstance(media_type, str) or not media_type:
                media_type = self._media_type(str(source_path)) or self._media_type(path)
            thumbnail_ref = frame or (path if self._media_type(path) == "image" else None)
            shots.append({"shot_id": f"shot-{fragment_id}", "order": len(shots) + 1, "business_label": str(label), "purpose": str(purpose), "status": "ready" if path else "not_ready", "media_type": media_type or "video", "thumbnail_ref": thumbnail_ref, "media_ref": path, "reference_media_ref": raw.get("reference_media_ref"), "claim_ids": [str(item) for item in (baseline_row.get("claim_ids") or [])], "fragment_id": fragment_id, "frame_available": frame is not None})
        elements = []
        for row in (baseline or {}).get("claims", []) if isinstance(baseline, Mapping) else []:
            if isinstance(row, Mapping):
                claim_id = str(row.get("claim_id") or row.get("id") or len(elements) + 1)
                related = claim_fragments.get(claim_id, [])
                frame = None
                for fragment_id in related:
                    candidate_frame = f"gate3_review_frames/{fragment_id}.jpg"
                    if self._exists(candidate_frame):
                        frame = candidate_frame
                        break
                elements.append({"element_id": f"element-{claim_id}", "business_label": str(row.get("label") or row.get("text") or "待确认"), "purpose": "卖点", "status": "ready", "media_type": "image" if frame else None, "thumbnail_ref": frame, "related_fragment_ids": related, "related_shot_ids": [f"shot-{fragment_id}" for fragment_id in related]})
        audio = self._audio_rows(evidence_by_fragment, voice_manifest)
        return {"elements": elements, "shots": shots, "audio": audio}

    def _audio_rows(self, evidence_by_fragment: Mapping[str, Any], voice_manifest: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        segments = {}
        if isinstance(voice_manifest, Mapping):
            raw_segments = voice_manifest.get("segments", [])
            if isinstance(raw_segments, list):
                segments = {str(item.get("fragment_id")): item for item in raw_segments if isinstance(item, Mapping) and item.get("fragment_id") is not None}
        result = []
        for index, (fragment_id, raw) in enumerate(evidence_by_fragment.items()):
            if not isinstance(raw, Mapping):
                continue
            segment = segments.get(fragment_id, {}) if isinstance(segments.get(fragment_id), Mapping) else {}
            voice_path = segment.get("path")
            media_ref = f"voice/{voice_path}" if isinstance(voice_path, str) and self._exists(f"voice/{voice_path}") else None
            measured = segment.get("measured_duration_seconds")
            result.append({"audio_id": f"audio-{fragment_id}", "business_label": str(raw.get("voice_text") or raw.get("narration") or raw.get("text") or f"口播 {index + 1}"), "purpose": "口播", "status": "ready" if media_ref else "预算", "media_type": "audio", "media_ref": media_ref, "measured_duration_seconds": measured if isinstance(measured, (int, float)) else None, "fragment_id": fragment_id})
        return result

    def _timeline(self, gate_id: str, recipe: Mapping[str, Any] | None, plan: Mapping[str, Any] | None, reconstruction: Mapping[str, Any] | None, final_validation: Mapping[str, Any] | None, render_report: Mapping[str, Any] | None, storyboard: Mapping[str, Any]) -> dict[str, Any]:
        source = "planned_order"
        rows: list[Mapping[str, Any]] = []
        if gate_id in {"gate3_material_selection", "gate3_evidence_closure"} and plan is not None:
            source, raw = "approved_broad_range", plan.get("fragments", [])
            rows = [row for row in raw if isinstance(row, Mapping)] if isinstance(raw, list) else []
        elif gate_id in {"gate4_pre_generation", "gate4_post_generation"} and reconstruction is not None:
            source, raw = "measured_reconstruction_timeline", reconstruction.get("fragments", [])
            rows = [row for row in raw if isinstance(row, Mapping)] if isinstance(raw, list) else []
        elif gate_id == "gate5" and (final_validation is not None or render_report is not None):
            source = "final_tracks"
            raw = (reconstruction or {}).get("fragments", [])
            rows = [row for row in raw if isinstance(row, Mapping)] if isinstance(raw, list) else []
        elif isinstance(recipe, Mapping):
            raw = recipe.get("shots", [])
            rows = [row for row in raw if isinstance(row, Mapping)] if isinstance(raw, list) else []
        label_by_fragment: dict[str, str] = {}
        thumb_by_fragment: dict[str, str | None] = {}
        for row in storyboard.get("shots", []):
            if not isinstance(row, Mapping):
                continue
            shot_id = str(row.get("shot_id", ""))
            if not shot_id.startswith("shot-"):
                continue
            key = shot_id[len("shot-"):]
            label = row.get("business_label")
            if isinstance(label, str) and label:
                label_by_fragment[key] = label
            thumb_by_fragment[key] = row.get("thumbnail_ref") if isinstance(row.get("thumbnail_ref"), str) else None
        picture = []
        voice = []
        subtitles = []
        for index, row in enumerate(rows):
            key = str(row.get("fragment_id") or row.get("shot_id") or index + 1)
            start = row.get("approved_broad_range", {}).get("start_seconds") if isinstance(row.get("approved_broad_range"), Mapping) else row.get("start_seconds", row.get("timeline_start_seconds"))
            end = row.get("approved_broad_range", {}).get("end_seconds") if isinstance(row.get("approved_broad_range"), Mapping) else row.get("end_seconds", row.get("timeline_end_seconds"))
            duration = round(end - start, 3) if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end >= start else None
            picture.append({"segment_id": f"timeline-shot-{key}", "label": label_by_fragment.get(key, row.get("text") or f"画面 {index + 1}"), "start_seconds": start, "end_seconds": end, "duration_seconds": duration, "related_object_id": f"shot-{key}", "thumbnail_ref": thumb_by_fragment.get(key)})
        measured = (reconstruction or {}).get("fragments", []) if isinstance(reconstruction, Mapping) else []
        for index, row in enumerate(measured if isinstance(measured, list) else []):
            if not isinstance(row, Mapping):
                continue
            fragment_id = str(row.get("fragment_id") or index + 1)
            start = row.get("timeline_start_seconds")
            end = row.get("timeline_end_seconds")
            duration = round(end - start, 3) if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end >= start else None
            text = str(row.get("text") or f"口播 {index + 1}")
            voice.append({"segment_id": f"timeline-voice-{fragment_id}", "label": text, "start_seconds": start, "end_seconds": end, "duration_seconds": duration, "related_object_id": f"audio-{fragment_id}", "thumbnail_ref": None})
            subtitles.append({"segment_id": f"timeline-subtitle-{fragment_id}", "label": text, "start_seconds": start, "end_seconds": end, "duration_seconds": duration, "related_object_id": f"shot-{fragment_id}", "thumbnail_ref": None})
        ends = [segment["end_seconds"] for segment in picture if isinstance(segment.get("end_seconds"), (int, float))]
        total_duration = round(max(ends), 3) if ends and source != "approved_broad_range" else None
        return {"source": source, "timebase": "source_range" if source == "approved_broad_range" else "output", "total_duration_seconds": total_duration, "tracks": [{"track_id": "picture", "kind": "画面", "segments": picture}, {"track_id": "voice", "kind": "口播", "segments": voice}, {"track_id": "subtitles", "kind": "字幕", "segments": subtitles}]}

    @staticmethod
    def _preview(gate_id: str, recipe: Mapping[str, Any] | None, allowlist: list[str]) -> dict[str, Any]:
        reference = None
        if isinstance(recipe, Mapping):
            candidates: list[str] = []
            reference_video = recipe.get("reference_video")
            if isinstance(reference_video, Mapping):
                candidate = reference_video.get("path")
                if isinstance(candidate, str) and candidate:
                    candidates.append(candidate)
            for key in ("reference_file", "reference_path"):
                candidate = recipe.get(key)
                if isinstance(candidate, str) and candidate:
                    candidates.append(candidate)
            for candidate in candidates:
                if candidate in allowlist:
                    reference = candidate
                    break
        proxy = "proxy.mp4" if "proxy.mp4" in allowlist else None
        final = "remix.mp4" if "remix.mp4" in allowlist else None
        if gate_id in {"gate1", "gate2"}:
            media_ref, mode = reference, "reference" if reference else "empty"
        elif gate_id in {"gate3_material_selection", "gate3_evidence_closure", "gate4_pre_generation", "gate4_post_generation"}:
            if proxy:
                media_ref, mode = proxy, "proxy"
            elif reference:
                media_ref, mode = reference, "reference"
            else:
                media_ref, mode = None, "empty"
        elif gate_id == "gate5":
            media_ref, mode = final, "final" if final else "empty"
        else:
            raise WorkspaceViewError(f"unsupported Gate: {gate_id}")
        preview: dict[str, Any] = {"mode": mode, "media_ref": media_ref, "status": "ready" if media_ref else "not_ready"}
        if media_ref is None:
            preview["empty_reason"] = "当前阶段主媒体尚未生成或缺失"
        return preview

    def _media_allowlist(self, gate_id: str, storyboard: Mapping[str, Any], timeline: Mapping[str, Any], brief: Mapping[str, Any] | None, recipe: Mapping[str, Any] | None) -> list[str]:
        values: set[str] = set()
        for row in storyboard.get("shots", []):
            if isinstance(row, Mapping):
                for key in ("media_ref", "reference_media_ref", "thumbnail_ref"):
                    value = row.get(key)
                    if isinstance(value, str) and self._safe_relative(value) and self._exists(value):
                        values.add(value)
        for row in storyboard.get("elements", []) if isinstance(storyboard.get("elements"), list) else []:
            if isinstance(row, Mapping) and isinstance(row.get("thumbnail_ref"), str) and self._exists(row["thumbnail_ref"]):
                values.add(row["thumbnail_ref"])
        for row in storyboard.get("audio", []) if isinstance(storyboard.get("audio"), list) else []:
            if isinstance(row, Mapping) and isinstance(row.get("media_ref"), str) and self._exists(row["media_ref"]):
                values.add(row["media_ref"])
        for track in timeline.get("tracks", []) if isinstance(timeline.get("tracks"), list) else []:
            for segment in track.get("segments", []) if isinstance(track, Mapping) and isinstance(track.get("segments"), list) else []:
                if isinstance(segment, Mapping) and isinstance(segment.get("thumbnail_ref"), str) and self._exists(segment["thumbnail_ref"]):
                    values.add(segment["thumbnail_ref"])
        candidates: list[str] = ["gate3_review_contact_sheet.jpg", "review_contact_sheet.jpg"] if gate_id in _MATERIAL_GATES else []
        if gate_id in {"gate3_material_selection", "gate3_evidence_closure", "gate4_pre_generation", "gate4_post_generation"}:
            candidates.append("proxy.mp4")
        if gate_id == "gate5":
            candidates.extend(("proxy.mp4", "remix.mp4"))
        for source in (recipe, brief):
            if not isinstance(source, Mapping):
                continue
            reference_video = source.get("reference_video")
            if isinstance(reference_video, Mapping) and isinstance(reference_video.get("path"), str) and reference_video["path"]:
                candidates.append(reference_video["path"])
            for key in ("reference_file", "reference_path"):
                candidate = source.get(key)
                if isinstance(candidate, str) and candidate:
                    candidates.append(candidate)
        for path in candidates:
            if self._safe_relative(path) and self._exists(path):
                values.add(path)
        directories = [self.root / "video_clips"]
        if gate_id in _MATERIAL_GATES:
            directories.extend((self.root / "media", self.root / "material", self.root / "gate3_review_frames", self.root / "gate3_review_proxies"))
        if gate_id in _VOICE_GATES:
            directories.append(self.root / "voice")
        for directory in directories:
            if directory.is_dir() and not directory.is_symlink():
                values.update(path.relative_to(self.root).as_posix() for path in directory.rglob("*") if path.is_file() and not path.is_symlink())
        return sorted(values)

    @staticmethod
    def _artifact_summary(gate_id: str, artifact: Mapping[str, Any] | None, kind: str) -> dict[str, Any] | None:
        if gate_id not in {"gate4_pre_generation", "gate4_post_generation", "gate5"} or artifact is None:
            return None
        return {"kind": kind, "status": str(artifact.get("lifecycle_status") or artifact.get("status") or "available"), "artifact_type": artifact.get("artifact_type")}

    @staticmethod
    def _script_details(gate_id: str, approved: Mapping[str, Any] | None, candidate: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if gate_id not in {"gate4_pre_generation", "gate4_post_generation"}:
            return None
        source = approved or candidate
        if source is None:
            return None
        lines = []
        for row in source.get("lines") or []:
            if isinstance(row, Mapping):
                lines.append({"fragment_id": str(row.get("fragment_id") or ""), "text": str(row.get("text") or "")})
        settings = source.get("tts_settings") if isinstance(source.get("tts_settings"), Mapping) else {}
        voice = None
        if settings:
            voice = {"provider": settings.get("provider"), "speaker": settings.get("speaker"), "speed": settings.get("speed")}
        return {"lifecycle_status": str(source.get("lifecycle_status") or "available"), "approved": approved is not None, "lines": lines, "voice": voice}

    @staticmethod
    def _voice_preflight_details(gate_id: str, preflight: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if gate_id not in {"gate4_pre_generation", "gate4_post_generation"} or preflight is None:
            return None
        fragments = []
        for row in preflight.get("fragments") or []:
            if isinstance(row, Mapping):
                fragments.append({key: row.get(key) for key in ("fragment_id", "preflight_status", "voice_duration_estimate_seconds", "visual_duration_budget_seconds", "voice_duration_margin_seconds")})
        return {"preflight_status": preflight.get("preflight_status"), "speed": preflight.get("speed"), "blocked_fragment_ids": list(preflight.get("blocked_fragment_ids") or []), "fragments": fragments}

    def _unclassified_assets(self, storyboard: Mapping[str, Any], allowlist: list[str]) -> list[dict[str, Any]]:
        selected = {row.get("media_ref") for row in storyboard.get("shots", []) if isinstance(row, Mapping) and isinstance(row.get("media_ref"), str)}
        result = []
        for path in allowlist:
            if path not in selected and (path.startswith("material/") or path.startswith("media/")):
                result.append({"asset_id": "asset-" + hashlib.sha256(path.encode()).hexdigest()[:16], "media_ref": path, "media_type": self._media_type(path), "reason": "尚未匹配", "replacement_eligible": False, "status": "unclassified"})
        return result

    @staticmethod
    def _section_states(gate_id: str, storyboard: Mapping[str, Any]) -> dict[str, str]:
        elements = "available" if storyboard.get("elements") else ("pending_gate2" if gate_id == "gate1" else "empty")
        shots = "available" if storyboard.get("shots") else "empty"
        audio = "available" if storyboard.get("audio") else ("pending_gate3" if gate_id in {"gate1", "gate2"} else "empty")
        return {"elements": elements, "shots": shots, "audio": audio}

    def _artifacts(self, state: Mapping[str, Any]) -> list[dict[str, Any]]:
        registered = state.get("artifacts") if isinstance(state.get("artifacts"), Mapping) else {}
        rows: list[dict[str, Any]] = []
        for name, (stage, label) in _BUSINESS_ARTIFACTS.items():
            record = registered.get(name)
            digest = record.get("sha256") if isinstance(record, Mapping) and isinstance(record.get("sha256"), str) else None
            if digest is None and self._exists(name):
                digest = self._file_sha256(name)
            media_ref = None
            if digest is not None and name.lower().endswith((*_IMAGE_EXT, *_VIDEO_EXT, *_AUDIO_EXT)):
                media_ref = name
            relations: dict[str, Any] = {}
            if name.endswith("_report.json") and digest is not None:
                report = self._optional_json(name)
                if isinstance(report, Mapping) and isinstance(report.get("input_hashes"), Mapping):
                    relations["inputs"] = sorted(str(key) for key in report["input_hashes"])
                    relations["outputs"] = [name]
            rows.append(
                {
                    "artifact_id": name,
                    "business_label": label,
                    "business_stage": stage,
                    "status": "available" if digest is not None else "pending",
                    "media_ref": media_ref,
                    "relations": relations,
                    "diagnostics": {"sha256": digest} if digest else {},
                }
            )
        return rows

    def _quality_checks(self, final_validation: Mapping[str, Any] | None, render_report: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        narrative = self._optional_json("narrative_coherence_report.json")
        visual = self._optional_json("visual_layout_report.json")
        preflight = self._optional_json("voice_preflight.json")
        checks: list[dict[str, Any]] = []
        checks.append(
            {
                "check_id": "narrative_coherence",
                "business_label": "叙事连贯性",
                "status": str(narrative.get("status")) if isinstance(narrative, Mapping) else "not_available",
                "source_artifact": "narrative_coherence_report.json" if isinstance(narrative, Mapping) else None,
                "detail": {
                    "checks": narrative.get("checks", {}) if isinstance(narrative, Mapping) else {},
                    "blocked_fragment_ids": narrative.get("blocked_fragment_ids", []) if isinstance(narrative, Mapping) else [],
                },
                "gate_scope": ["gate4_pre_generation", "gate4_post_generation", "gate5"],
            }
        )
        checks.append(
            {
                "check_id": "visual_layout",
                "business_label": "图片布局与文字可读性",
                "status": str(visual.get("status")) if isinstance(visual, Mapping) else "not_available",
                "source_artifact": "visual_layout_report.json" if isinstance(visual, Mapping) else None,
                "detail": {
                    "blocked_fragment_ids": visual.get("blocked_fragment_ids", []) if isinstance(visual, Mapping) else [],
                    "readability": [row.get("readability_status") for row in visual.get("fragments", [])] if isinstance(visual, Mapping) else [],
                },
                "gate_scope": ["gate4_pre_generation", "gate4_post_generation", "gate5"],
            }
        )
        checks.append(
            {
                "check_id": "voice_preflight",
                "business_label": "声音预算检查",
                "status": str(preflight.get("preflight_status")) if isinstance(preflight, Mapping) and preflight.get("preflight_status") else "not_available",
                "source_artifact": "voice_preflight.json" if isinstance(preflight, Mapping) else None,
                "detail": {"blocked_fragment_ids": list(preflight.get("blocked_fragment_ids") or [])} if isinstance(preflight, Mapping) else {},
                "gate_scope": ["gate4_pre_generation", "gate4_post_generation", "gate5"],
            }
        )
        hard = final_validation.get("hard_gate_checks") if isinstance(final_validation, Mapping) else None
        if isinstance(hard, Mapping) and hard:
            values = [str(value) for value in hard.values()]
            l0_status = "passed" if all(value == "passed" for value in values) else "blocked"
        else:
            hard, l0_status = {}, "not_available"
        checks.append(
            {
                "check_id": "l0",
                "business_label": "L0 成片技术校验",
                "status": l0_status,
                "source_artifact": "final_validation_report.json" if isinstance(final_validation, Mapping) else None,
                "detail": hard,
                "gate_scope": ["gate5"],
            }
        )
        audit = render_report.get("production_audit") if isinstance(render_report, Mapping) else None
        checks.append(
            {
                "check_id": "production_audit",
                "business_label": "P 生产审计",
                "status": str(audit.get("status")) if isinstance(audit, Mapping) and audit.get("status") else ("passed" if isinstance(audit, Mapping) and audit else "not_available"),
                "source_artifact": "render_report.json" if isinstance(audit, Mapping) else None,
                "detail": audit if isinstance(audit, Mapping) else {},
                "gate_scope": ["gate5"],
            }
        )
        snapshot = self._latest_score_snapshot()
        checks.append(
            {
                "check_id": "l1",
                "business_label": "L1 质量评分",
                "status": str(snapshot.get("measurement_status")) if isinstance(snapshot, Mapping) and snapshot.get("measurement_status") else "not_available",
                "source_artifact": "phase6_score_snapshot" if isinstance(snapshot, Mapping) else None,
                "detail": snapshot if isinstance(snapshot, Mapping) else {},
                "gate_scope": ["gate5"],
            }
        )
        return checks

    def _latest_score_snapshot(self) -> Mapping[str, Any] | None:
        measurements = self.root / "measurements"
        if not measurements.is_dir() or measurements.is_symlink():
            return None
        latest: Mapping[str, Any] | None = None
        latest_name = ""
        for path in measurements.glob("*/phase6_score_snapshot.json"):
            if path.is_file() and not path.is_symlink() and path.name > latest_name:
                try:
                    latest = read_json_object(path)
                    latest_name = path.name
                except StorageError:
                    continue
        return latest

    def _execution(self) -> list[dict[str, Any]]:
        metrics_path = self.root / "stage_metrics.jsonl"
        if metrics_path.is_symlink() or not metrics_path.is_file():
            return []
        latest: dict[str, Mapping[str, Any]] = {}
        for record in read_jsonl_records(metrics_path):
            if not isinstance(record, Mapping):
                continue
            stage_id = record.get("execution_stage_id")
            if not isinstance(stage_id, str) or not stage_id:
                continue
            existing = latest.get(stage_id)
            recorded = str(record.get("recorded_at", ""))
            if existing is None or recorded >= str(existing.get("recorded_at", "")):
                latest[stage_id] = record
        rows = [
            {
                "stage_id": stage_id,
                "business_label": _STAGE_BUSINESS.get(stage_id, stage_id),
                "status": str(record.get("status", "")),
                "attempt_id": record.get("attempt_id"),
                "wall_seconds": record.get("wall_seconds"),
                "cache_status": record.get("cache_status"),
                "recorded_at": record.get("recorded_at"),
                "failure_reason": record.get("failure_category"),
            }
            for stage_id, record in latest.items()
        ]
        from .orchestrator import dag_for_task

        order = [node.node_id for node in dag_for_task(self.root)]
        rows.sort(key=lambda row: order.index(row["stage_id"]) if row["stage_id"] in order else len(order))
        return rows

    def _file_sha256(self, relative: str) -> str:
        with (self.root / relative).open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    @staticmethod
    def _required_files(gate_id: str) -> tuple[str, ...]:
        return {"gate1": ("recipe.json",), "gate2": ("content_baseline.json", "mutation_plan.json", "shot_blueprint.json"), "gate3_material_selection": ("matches.json", "fragment_plan.json"), "gate3_evidence_closure": ("script_evidence_matrix.json",), "gate4_pre_generation": ("production_script_candidate.json", "voice_preflight.json"), "gate4_post_generation": ("voice/voice_manifest.json", "reconstruction_timeline.json", "captions.srt"), "gate5": ("remix.mp4", "final_validation_report.json", "render_report.json", "captions.srt")}[gate_id]

    @staticmethod
    def _decision_evidence(gate_id: str, missing: list[str], *artifacts: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        names = {"gate1": ("recipe.json",), "gate2": ("content_baseline.json", "mutation_plan.json", "shot_blueprint.json"), "gate3_material_selection": ("matches.json", "fragment_plan.json"), "gate3_evidence_closure": ("script_evidence_matrix.json",), "gate4_pre_generation": ("production_script_candidate.json", "voice_preflight.json"), "gate4_post_generation": ("voice/voice_manifest.json", "reconstruction_timeline.json", "captions.srt"), "gate5": ("final_validation_report.json", "render_report.json", "captions.srt", "remix.mp4")}[gate_id]
        return [{"artifact": name, "status": "missing" if name in missing else "available"} for name in names]

    @staticmethod
    def _safe_relative(value: str) -> bool:
        path = Path(value)
        return not path.is_absolute() and ".." not in path.parts and "\\" not in value
