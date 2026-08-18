"""Deterministic business-facing workspace projection over canonical run artifacts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .snapshot_schema_validator import SnapshotSchemaValidator
from .storage import StorageError, read_json_object


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
)


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
        preflight = self._optional_json("voice_preflight.json")
        reconstruction = self._optional_json("reconstruction_timeline.json")
        final_validation = self._optional_json("final_validation_report.json")
        render_report = self._optional_json("render_report.json")
        storyboard = self._storyboard(recipe, blueprint, baseline, matches, fragment_plan, evidence_matrix, state)
        timeline = self._timeline(gate_id, recipe, fragment_plan, reconstruction, final_validation, render_report, storyboard)
        media_allowlist = self._media_allowlist(storyboard, timeline, brief, recipe)
        required = self._required_files(gate_id)
        missing = [name for name in required if not self._exists(name)]
        blockers = [item for item in state.get("blockers", []) if isinstance(item, Mapping) and item.get("requires_user", True)]
        lifecycle = "not_ready" if missing or blockers or state.get("gate_status", {}).get(gate_id) == "not_ready" else "ready"
        task = self._text(brief, ("task_name", "name", "title")) or "待确认"
        product = self._text(brief, ("product_name", "product", "product_label")) or "待确认"
        platform = self._text(brief, ("platform", "target_platform")) or "待确认"
        progress = round((stage_index + (1 if lifecycle == "ready" else 0)) / len(_BUSINESS_STAGES), 2)
        statuses = state.get("gate_status") if isinstance(state.get("gate_status"), Mapping) else {}
        stages = []
        for business_label, gates in _BUSINESS_STAGES:
            gate_rows = [{"gate_id": gate, "status": str(statuses.get(gate, "not_ready"))} for gate in gates]
            stage_status = "approved" if all(row["status"] == "approved" for row in gate_rows) else ("awaiting_user" if any(row["status"] == "awaiting_user" for row in gate_rows) else "not_ready")
            stages.append({"stage_id": f"stage{len(stages) + 1}", "business_label": business_label, "gate_ids": list(gates), "status": stage_status, "substeps": gate_rows})
        evidence = self._decision_evidence(gate_id, missing, recipe, baseline, mutation, matches, fragment_plan, evidence_matrix, preflight, reconstruction, final_validation, render_report)
        recommendation = "建议通过当前已具备的审核内容。" if not missing and not blockers else "待确认：请先补齐缺失事实或处理阻塞。"
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
            "preview": self._preview(gate_id, recipe, final_validation, media_allowlist),
            "timeline": timeline,
            "process": {"current_stage": label, "current_gate": gate_id, "stages": stages},
            "decision_context": {
                "question": _GATE_QUESTIONS[gate_id], "recommendation": recommendation,
                "evidence": evidence, "risks": [str(item.get("detail") or item.get("category") or "待确认阻塞") for item in blockers],
                "next_action": "补齐缺失事实并重新审核" if missing or blockers else "选择通过、要求修改或驳回",
                "approval_eligibility": not missing and not blockers and lifecycle == "ready",
                "missing_artifacts": missing,
                "claims": {
                    "approved": [row for row in (baseline or {}).get("claims", []) if isinstance(row, Mapping) and row.get("status", "approved") != "forbidden"] if gate_id == "gate2" else [],
                    "forbidden": list((mutation or {}).get("forbidden_claims", [])) if gate_id == "gate2" and isinstance(mutation, Mapping) else [],
                },
                "structure": list((baseline or {}).get("fragments", [])) if gate_id == "gate2" and isinstance(baseline, Mapping) else [],
                "source_text_treatment": list((matches or {}).get("source_text_treatment", [])) if gate_id in {"gate3_material_selection", "gate3_evidence_closure"} and isinstance(matches, Mapping) else [],
                "evidence_coverage": (evidence_matrix or {}).get("coverage", []) if gate_id == "gate3_evidence_closure" and isinstance(evidence_matrix, Mapping) else [],
                "missing_objects": list((matches or {}).get("missing_objects", [])) if gate_id in {"gate3_material_selection", "gate3_evidence_closure"} and isinstance(matches, Mapping) else [],
                "production_script": self._artifact_summary(gate_id, (self._optional_json("approved_production_script.json") or self._optional_json("production_script_candidate.json")), "script"),
                "voice_preflight": self._artifact_summary(gate_id, preflight, "voice_preflight"),
                "generated_voice": self._artifact_summary(gate_id, self._optional_json("voice/voice_manifest.json"), "voice"),
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

    def _storyboard(self, recipe: Mapping[str, Any] | None, blueprint: Mapping[str, Any] | None, baseline: Mapping[str, Any] | None, matches: Mapping[str, Any] | None, plan: Mapping[str, Any] | None, evidence: Mapping[str, Any] | None, state: Mapping[str, Any]) -> dict[str, Any]:
        recipe_shots = recipe.get("shots", []) if isinstance(recipe, Mapping) else []
        if not isinstance(recipe_shots, list):
            recipe_shots = []
        fragments = (plan or {}).get("fragments", []) if isinstance(plan, Mapping) else []
        if not isinstance(fragments, list) or not fragments:
            fragments = (blueprint or {}).get("fragments", []) if isinstance(blueprint, Mapping) else []
        if not isinstance(fragments, list):
            fragments = []
        match_rows = {str(row.get("fragment_id")): row for row in (matches or {}).get("fragments", []) if isinstance(row, Mapping) and row.get("fragment_id") is not None}
        shots: list[dict[str, Any]] = []
        for index, raw in enumerate(recipe_shots):
            if not isinstance(raw, Mapping):
                continue
            raw_id = str(raw.get("shot_id") or raw.get("id") or index + 1)
            reference_ref = raw.get("media_ref") or raw.get("path")
            shots.append({"shot_id": f"shot-{raw_id}", "order": index + 1, "business_label": str(raw.get("label") or raw.get("title") or "待确认"), "purpose": str(raw.get("purpose") or raw.get("narrative_role") or "待确认"), "status": "ready", "thumbnail_ref": reference_ref if isinstance(reference_ref, str) else None, "reference_media_ref": reference_ref if isinstance(reference_ref, str) else None, "start_seconds": raw.get("start_seconds"), "end_seconds": raw.get("end_seconds")})
        for index, raw in enumerate(fragments):
            if not isinstance(raw, Mapping):
                continue
            fragment_id = str(raw.get("fragment_id") or raw.get("id") or index + 1)
            row = match_rows.get(fragment_id, {})
            candidate = row.get("selected_candidate") if isinstance(row, Mapping) else None
            if not isinstance(candidate, Mapping):
                candidates = row.get("candidates", []) if isinstance(row, Mapping) else []
                candidate = candidates[0] if isinstance(candidates, list) and candidates and isinstance(candidates[0], Mapping) else {}
            path = candidate.get("path") if isinstance(candidate, Mapping) else None
            shots.append({"shot_id": f"shot-{fragment_id}", "order": len(shots) + 1, "business_label": str(raw.get("label") or raw.get("title") or fragment_id), "purpose": str(raw.get("narration") or raw.get("purpose") or "待确认"), "status": "ready" if path else "not_ready", "thumbnail_ref": path if isinstance(path, str) else None, "media_ref": path if isinstance(path, str) else None, "reference_media_ref": raw.get("reference_media_ref")})
        elements = []
        for row in (baseline or {}).get("claims", []) if isinstance(baseline, Mapping) else []:
            if isinstance(row, Mapping):
                claim_id = str(row.get("claim_id") or row.get("id") or len(elements) + 1)
                elements.append({"element_id": f"element-{claim_id}", "business_label": str(row.get("label") or row.get("text") or "待确认"), "purpose": "卖点", "status": "ready"})
        audio = self._audio_rows(evidence, baseline)
        return {"elements": elements, "shots": shots, "audio": audio}

    @staticmethod
    def _audio_rows(evidence: Mapping[str, Any] | None, baseline: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        rows = (evidence or {}).get("rows", []) if isinstance(evidence, Mapping) else []
        if not isinstance(rows, list):
            rows = []
        result = []
        for index, raw in enumerate(rows):
            if isinstance(raw, Mapping):
                fragment_id = str(raw.get("fragment_id") or index + 1)
                result.append({"audio_id": f"audio-{fragment_id}", "business_label": str(raw.get("narration") or raw.get("text") or "待确认"), "purpose": "口播", "status": "ready"})
        return result

    def _timeline(self, gate_id: str, recipe: Mapping[str, Any] | None, plan: Mapping[str, Any] | None, reconstruction: Mapping[str, Any] | None, final_validation: Mapping[str, Any] | None, render_report: Mapping[str, Any] | None, storyboard: Mapping[str, Any]) -> dict[str, Any]:
        source = "planned_order"
        rows: list[Mapping[str, Any]] = []
        if gate_id in {"gate3_material_selection", "gate3_evidence_closure"} and isinstance(plan, Mapping):
            source, raw = "approved_broad_range", plan.get("fragments", [])
            rows = [row for row in raw if isinstance(row, Mapping)] if isinstance(raw, list) else []
        elif gate_id in {"gate4_pre_generation", "gate4_post_generation"} and isinstance(reconstruction, Mapping):
            source, raw = "measured_reconstruction_timeline", reconstruction.get("fragments", [])
            rows = [row for row in raw if isinstance(row, Mapping)] if isinstance(raw, list) else []
        elif gate_id == "gate5" and (final_validation or render_report):
            source = "final_tracks"
            raw = (reconstruction or {}).get("fragments", [])
            rows = [row for row in raw if isinstance(row, Mapping)] if isinstance(raw, list) else []
        elif isinstance(recipe, Mapping):
            raw = recipe.get("shots", [])
            rows = [row for row in raw if isinstance(row, Mapping)] if isinstance(raw, list) else []
        picture = []
        for index, row in enumerate(rows):
            start = row.get("approved_broad_range", {}).get("start_seconds") if isinstance(row.get("approved_broad_range"), Mapping) else row.get("start_seconds", row.get("timeline_start_seconds"))
            end = row.get("approved_broad_range", {}).get("end_seconds") if isinstance(row.get("approved_broad_range"), Mapping) else row.get("end_seconds", row.get("timeline_end_seconds"))
            picture.append({"segment_id": f"timeline-shot-{row.get('fragment_id') or row.get('shot_id') or index + 1}", "label": str(row.get("purpose") or row.get("narration") or "待确认"), "start_seconds": start, "end_seconds": end})
        return {"source": source, "tracks": [{"track_id": "picture", "kind": "画面", "segments": picture}, {"track_id": "voice", "kind": "口播", "segments": []}, {"track_id": "subtitles", "kind": "字幕", "segments": []}]}

    @staticmethod
    def _preview(gate_id: str, recipe: Mapping[str, Any] | None, final_validation: Mapping[str, Any] | None, allowlist: list[str]) -> dict[str, Any]:
        preferred = "remix.mp4" if gate_id == "gate5" and "remix.mp4" in allowlist else "reference-" + str((recipe or {}).get("reference_file", "video.mp4"))
        return {"mode": "final" if gate_id == "gate5" else "reference", "media_ref": preferred if preferred in allowlist else None, "status": "ready" if preferred in allowlist else "not_ready"}

    def _media_allowlist(self, storyboard: Mapping[str, Any], timeline: Mapping[str, Any], brief: Mapping[str, Any] | None, recipe: Mapping[str, Any] | None) -> list[str]:
        values: set[str] = set()
        for row in storyboard.get("shots", []):
            if isinstance(row, Mapping):
                for key in ("media_ref", "reference_media_ref"):
                    value = row.get(key)
                    if isinstance(value, str) and self._safe_relative(value) and self._exists(value):
                        values.add(value)
        reference = (recipe or {}).get("reference_file") or (recipe or {}).get("reference_path") or (brief or {}).get("reference_file") or (brief or {}).get("reference_path")
        candidates = ["remix.mp4"]
        if isinstance(reference, str) and reference:
            candidates.append(reference)
        for path in candidates:
            if self._safe_relative(path) and self._exists(path):
                values.add(path)
        for directory in (self.root / "media", self.root / "material", self.root / "video_clips"):
            if directory.is_dir() and not directory.is_symlink():
                values.update(path.relative_to(self.root).as_posix() for path in directory.rglob("*") if path.is_file() and not path.is_symlink())
        return sorted(values)

    @staticmethod
    def _artifact_summary(gate_id: str, artifact: Mapping[str, Any] | None, kind: str) -> dict[str, Any] | None:
        if gate_id not in {"gate4_pre_generation", "gate4_post_generation", "gate5"} or artifact is None:
            return None
        return {"kind": kind, "status": str(artifact.get("lifecycle_status") or artifact.get("status") or "available"), "artifact_type": artifact.get("artifact_type")}

    def _unclassified_assets(self, storyboard: Mapping[str, Any], allowlist: list[str]) -> list[dict[str, Any]]:
        selected = {row.get("media_ref") for row in storyboard.get("shots", []) if isinstance(row, Mapping) and isinstance(row.get("media_ref"), str)}
        result = []
        for path in allowlist:
            if path not in selected and not path.startswith("reference-") and path != "remix.mp4":
                result.append({"asset_id": "asset-" + hashlib.sha256(path.encode()).hexdigest()[:16], "media_ref": path, "reason": "尚未匹配", "replacement_eligible": False, "status": "unclassified"})
        return result

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
