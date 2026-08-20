"""Auditable previews and atomic structured-change submissions."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import statistics
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .review_session import ReviewSessionError, ReviewSessionService
from .run_registry import RunRegistry, RunRegistryError
from .snapshot_schema_validator import SnapshotSchemaError, SnapshotSchemaValidator
from .stage_input_validator import StageInputValidator
from .storage import (
    RevisionConflict,
    StorageError,
    TaskStorage,
    atomic_write_json,
    read_json_object,
)
from .transactions import ArtifactPromotion, TransactionManager


class ChangeConflict(StorageError):
    """Raised when a change is invalid, stale, or conflicts with prior intent."""


_SCHEMA_NAMES = {
    "copy": "changes/copy.schema.json",
    "claim_scope": "changes/claim-scope.schema.json",
    "voice": "changes/voice.schema.json",
    "material": "changes/material.schema.json",
    "range": "changes/range.schema.json",
    "rerecord": "changes/rerecord.schema.json",
    "boundary": "changes/boundary.schema.json",
    "structural": "changes/structural.schema.json",
    "script_candidate_select": "changes/script-candidate-select.schema.json",
}

_IMPACTS: dict[str, dict[str, object]] = {
    "copy": {
        "earliest_affected_gate": "gate4_pre_generation",
        "stale_gates": ["gate4_pre_generation", "gate4_post_generation", "gate4", "gate5"],
        "stale_stages": ["build-narrative-coherence", "build-production-script", "voice-preflight", "build-gate4-pre-package", "generate-voice", "build-reconstruction-timeline", "build-gate4-post-package", "summarize-gate4", "render-proxy", "validate-proxy-boundaries", "render-final", "build-gate5-package"],
        "artifacts_to_regenerate": ["production_script_candidate.json", "narrative_coherence_report.json", "voice_preflight.json", "voice/", "reconstruction_timeline.json", "captions.srt", "remix.mp4"],
        "media_actions": ["regenerate_voice", "rebuild_timeline", "rerender"],
        "requires_tts": True,
        "requires_render": True,
        "quality_dimensions_affected": ["copy_accuracy", "evidence_alignment", "voice_quality", "rhythm", "delivery_integrity"],
        "business_explanation": "文案变化会使生成前审核及其后续语音、时间轴和成片失效。",
        "recovery_path": "重新编译脚本并预检，从 Gate 4 生成前重新审核。",
    },
    "script_candidate_select": {
        "earliest_affected_gate": "gate4_pre_generation",
        "stale_gates": ["gate4_pre_generation", "gate4_post_generation", "gate4", "gate5"],
        "stale_stages": ["build-production-script", "voice-preflight", "build-gate4-pre-package", "generate-voice", "build-reconstruction-timeline", "build-gate4-post-package", "summarize-gate4", "render-proxy", "validate-proxy-boundaries", "render-final", "build-gate5-package"],
        "artifacts_to_regenerate": ["production_script_candidate.json", "voice_preflight.json", "voice/", "reconstruction_timeline.json", "captions.srt", "remix.mp4"],
        "media_actions": ["regenerate_voice", "rebuild_timeline", "rerender"],
        "requires_tts": True,
        "requires_render": True,
        "quality_dimensions_affected": ["copy_accuracy", "evidence_alignment", "rhythm", "delivery_integrity"],
        "business_explanation": "切换已通过的脚本候选会重新物化生产脚本和配音预检，并使 Gate 4 及成片失效。",
        "recovery_path": "返回 Gate 4 生成前重新审核选中的脚本候选。",
    },
    "claim_scope": {
        "earliest_affected_gate": "gate2",
        "stale_gates": ["gate2", "gate3_material_selection", "gate3_evidence_closure", "gate3", "gate4_pre_generation", "gate4_post_generation", "gate4", "gate5"],
        "stale_stages": ["compile-blueprint", "compile-mutation-plan", "lint-gate2-package", "build-material-evidence-requirements", "build-coverage-authoritative", "match-assets", "build-material-selection-package", "freeze-fragment-plan", "validate-script-evidence", "summarize-gate3", "build-narrative-coherence", "build-production-script", "materialize-approved-broad", "validate-visual-layout", "voice-preflight", "build-gate4-pre-package", "generate-voice", "build-reconstruction-timeline", "build-gate4-post-package", "summarize-gate4", "render-proxy", "validate-proxy-boundaries", "render-final", "build-gate5-package"],
        "artifacts_to_regenerate": ["content_baseline.json", "mutation_plan.json", "material_evidence_requirements.json", "material_evidence_annotations.json", "coverage_report.json", "matches.json", "fragment_plan.json", "script_evidence_matrix.json", "production_script_candidate.json", "narrative_coherence_report.json", "visual_layout_report.json", "voice_preflight.json", "voice/", "reconstruction_timeline.json", "captions.srt", "remix.mp4"],
        "media_actions": ["rematch_materials", "regenerate_voice", "rerender"],
        "requires_tts": True,
        "requires_render": True,
        "quality_dimensions_affected": ["claim_compliance", "evidence_alignment", "content_quality", "delivery_integrity"],
        "business_explanation": "声明范围属于 Gate 2 内容合同，变化后全部下游证据和媒体必须重建。",
        "recovery_path": "返回 Gate 2 重新批准内容基线与变更包。",
    },
    "voice": {
        "earliest_affected_gate": "gate4_pre_generation",
        "stale_gates": ["gate4_pre_generation", "gate4_post_generation", "gate4", "gate5"],
        "stale_stages": ["voice-preflight", "build-gate4-pre-package", "generate-voice", "build-reconstruction-timeline", "build-gate4-post-package", "summarize-gate4", "render-proxy", "validate-proxy-boundaries", "render-final", "build-gate5-package"],
        "artifacts_to_regenerate": ["approved_production_script.json", "voice/", "reconstruction_timeline.json", "captions.srt", "remix.mp4"],
        "media_actions": ["regenerate_voice", "rebuild_timeline", "rerender"],
        "requires_tts": True,
        "requires_render": True,
        "quality_dimensions_affected": ["voice_quality", "rhythm", "caption_sync", "delivery_integrity"],
        "business_explanation": "音色或语速变化需要重新预检、生成语音并重建时间轴。",
        "recovery_path": "从 Gate 4 生成前重新审核语音设置。",
    },
    "material": {
        "earliest_affected_gate": "gate3_material_selection",
        "stale_gates": ["gate3_material_selection", "gate3_evidence_closure", "gate3", "gate4_pre_generation", "gate4_post_generation", "gate4", "gate5"],
        "stale_stages": ["build-material-selection-package", "freeze-fragment-plan", "validate-script-evidence", "summarize-gate3", "build-narrative-coherence", "build-production-script", "materialize-approved-broad", "validate-visual-layout", "voice-preflight", "build-gate4-pre-package", "generate-voice", "build-reconstruction-timeline", "build-gate4-post-package", "summarize-gate4", "render-proxy", "validate-proxy-boundaries", "render-final", "build-gate5-package"],
        "artifacts_to_regenerate": ["matches.json", "fragment_plan.json", "material_manifest.json", "script_evidence_matrix.json", "production_script_candidate.json", "narrative_coherence_report.json", "visual_layout_report.json", "voice_preflight.json", "voice/", "reconstruction_timeline.json", "captions.srt", "remix.mp4"],
        "media_actions": ["rematerialize", "regenerate_voice", "rerender"],
        "requires_tts": True,
        "requires_render": True,
        "quality_dimensions_affected": ["visual_relevance", "evidence_alignment", "rhythm", "delivery_integrity"],
        "business_explanation": "素材变化会使 Gate 3 证据闭环和全部下游媒体失效。",
        "recovery_path": "重建 Gate 3 选材包并重新完成证据闭环。",
    },
    "range": {},
    "rerecord": {
        "earliest_affected_gate": "gate4_post_generation",
        "stale_gates": ["gate4_post_generation", "gate4", "gate5"],
        "stale_stages": ["generate-voice", "build-reconstruction-timeline", "build-gate4-post-package", "summarize-gate4", "render-proxy", "validate-proxy-boundaries", "render-final", "build-gate5-package"],
        "artifacts_to_regenerate": ["voice/", "reconstruction_timeline.json", "captions.srt", "remix.mp4"],
        "media_actions": ["rerecord_selected", "rebuild_timeline", "rerender"],
        "requires_tts": True,
        "requires_render": True,
        "quality_dimensions_affected": ["voice_quality", "caption_sync", "rhythm", "delivery_integrity"],
        "business_explanation": "指定句重录保留批准文案，但生成后语音、时间轴和成片必须更新。",
        "recovery_path": "重录指定句并返回 Gate 4 生成后听审。",
    },
    "boundary": {
        "earliest_affected_gate": "gate5",
        "stale_gates": ["gate5"],
        "stale_stages": ["render-proxy", "validate-proxy-boundaries", "render-final", "build-gate5-package"],
        "artifacts_to_regenerate": ["proxy_boundary_report.json", "render_report.json", "final_validation_report.json", "remix.mp4"],
        "media_actions": ["rebuild_proxy", "rerender"],
        "requires_tts": False,
        "requires_render": True,
        "quality_dimensions_affected": ["boundary_quality", "delivery_integrity"],
        "business_explanation": "边界问题只使 Gate 5 代理检查、渲染和最终校验失效。",
        "recovery_path": "修复指定边界后重新代理检查并渲染。",
    },
    "structural": {
        "earliest_affected_gate": "gate2",
        "stale_gates": ["gate2", "gate3_material_selection", "gate3_evidence_closure", "gate3", "gate4_pre_generation", "gate4_post_generation", "gate4", "gate5"],
        "stale_stages": ["compile-blueprint", "compile-mutation-plan", "lint-gate2-package", "build-material-evidence-requirements", "build-coverage-authoritative", "match-assets", "build-material-selection-package", "freeze-fragment-plan", "validate-script-evidence", "summarize-gate3", "build-narrative-coherence", "build-production-script", "materialize-approved-broad", "validate-visual-layout", "voice-preflight", "build-gate4-pre-package", "generate-voice", "build-reconstruction-timeline", "build-gate4-post-package", "summarize-gate4", "render-proxy", "validate-proxy-boundaries", "render-final", "build-gate5-package"],
        "artifacts_to_regenerate": ["content_baseline.json", "mutation_plan.json", "material_evidence_requirements.json", "material_evidence_annotations.json", "narrative_coherence_report.json"],
        "media_actions": [],
        "requires_tts": False,
        "requires_render": False,
        "quality_dimensions_affected": ["content_quality", "claim_compliance", "evidence_alignment"],
        "business_explanation": "结构变化只能形成 Gate 2 修改请求，不能在当前 Gate 直接执行。",
        "recovery_path": "返回 Gate 2 修改并重新批准内容合同。",
    },
}
_IMPACTS["range"] = copy.deepcopy(_IMPACTS["material"])
_IMPACTS["range"]["business_explanation"] = "源范围变化会使 Gate 3 证据闭环和全部下游媒体失效。"

_TERMINAL_NODES = frozenset({"archive-approved"})


def dag_downstream_closure(start_ids: list[str], *, exclude: frozenset[str] = _TERMINAL_NODES) -> list[str]:
    """Compute the downstream stage closure from the current production DAG.

    Explicit impact lists must stay consistent with this closure; tests compare
    the two so a DAG change cannot silently diverge from the invalidation tables.
    """
    from .orchestrator import default_dag

    nodes = {node.node_id: node for node in default_dag()}
    closure: list[str] = []
    seen: set[str] = set()
    queue: list[str] = list(start_ids)
    while queue:
        node_id = queue.pop(0)
        if node_id in seen or node_id in exclude:
            continue
        seen.add(node_id)
        closure.append(node_id)
        if node_id not in nodes:
            continue
        for candidate in nodes.values():
            if node_id in candidate.dependencies:
                queue.append(candidate.node_id)
    return closure


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class _ChangeValidator:
    def __init__(self, root: Path, *, actor: str, role: str) -> None:
        self.root = root
        self.actor = actor
        self.role = role
        self.sessions = ReviewSessionService(root, actor=actor, role=role)
        self.schemas = SnapshotSchemaValidator()

    def validate(self, session_id: str, gate_id: str, request: Mapping[str, object]) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            session = self.sessions.get(session_id)
        except ReviewSessionError as error:
            raise ChangeConflict(str(error)) from error
        identity = session.get("review_identity")
        if not isinstance(identity, Mapping) or identity.get("gate_id") != gate_id:
            raise ChangeConflict("session gate mismatch")
        state = TaskStorage(self.root).read_state()
        if identity.get("run_id") != state.get("run_id") or identity.get("state_revision") != state.get("state_revision"):
            raise ChangeConflict("review identity is stale")
        try:
            package_hash = self.sessions.package_hash(gate_id)
        except ReviewSessionError as error:
            raise ChangeConflict(str(error)) from error
        if identity.get("review_package_hash") != package_hash:
            raise ChangeConflict("review package hash is stale")
        if not isinstance(request, Mapping):
            raise ChangeConflict("change request must be an object")
        normalized = copy.deepcopy(dict(request))
        change_type = normalized.get("change_type")
        schema_name = _SCHEMA_NAMES.get(change_type) if isinstance(change_type, str) else None
        if schema_name is None:
            raise ChangeConflict("change type is unsupported")
        try:
            self.schemas.assert_valid(normalized, schema_name)
        except (SnapshotSchemaError, OSError) as error:
            raise ChangeConflict(f"change request is invalid: {error}") from error
        self._validate_source(normalized)
        if normalized.get("change_type") == "script_candidate_select" and gate_id != "gate4_pre_generation":
            raise ChangeConflict("script candidate selection is only allowed at gate4_pre_generation")
        return normalized, dict(identity)

    def _validate_source(self, request: Mapping[str, object]) -> None:
        change_type = str(request["change_type"])
        payload = request["payload"]
        assert isinstance(payload, Mapping)
        scope_ids = request.get("scope_ids")
        if not isinstance(scope_ids, list) or any(not isinstance(item, str) or not item for item in scope_ids) or len(scope_ids) != len(set(scope_ids)):
            raise ChangeConflict("scope ids are invalid")
        if change_type == "copy":
            self._validate_copy(payload, scope_ids)
        elif change_type == "claim_scope":
            self._validate_claim_scope(payload, scope_ids)
        elif change_type == "voice":
            self._validate_voice(payload)
        elif change_type == "range":
            self._validate_range(payload)
            self._match_scope(scope_ids, [payload.get("fragment_id")])
        elif change_type == "material":
            self._validate_material(payload)
            self._match_scope(scope_ids, [payload.get("fragment_id")])
        elif change_type == "rerecord":
            self._validate_rerecord(payload, scope_ids)
        elif change_type == "boundary":
            self._validate_boundary(payload, scope_ids)
        elif change_type == "structural":
            self._validate_structural(payload, scope_ids)
        elif change_type == "script_candidate_select":
            self._validate_script_candidate_select(payload, scope_ids)

    def _validate_copy(self, payload: Mapping[str, object], scope_ids: list[str]) -> None:
        line_ids = payload.get("line_ids")
        text_by_id = payload.get("text_by_id")
        if not isinstance(line_ids, list) or not isinstance(text_by_id, Mapping):
            raise ChangeConflict("copy line ids are invalid")
        self._match_scope(scope_ids, line_ids)
        if set(text_by_id) != set(line_ids):
            raise ChangeConflict("copy text must match the selected line ids")
        candidate = read_json_object(self.root / "production_script_candidate.json")
        allowed = self._ids(candidate.get("lines"), "line_id")
        if not set(line_ids).issubset(allowed):
            raise ChangeConflict("copy line is not allowlisted")
        intent = payload.get("edit_intent")
        is_v1_task = candidate.get("contract_version") is None and candidate.get("schema_version") == "1.0"
        if intent is not None:
            if intent not in {"bridge", "rewrite"}:
                raise ChangeConflict("copy edit_intent must be bridge or rewrite")
        elif is_v1_task:
            payload["edit_intent"] = "rewrite"
        else:
            raise ChangeConflict("copy edit_intent is required (bridge|rewrite)")

    def _validate_claim_scope(self, payload: Mapping[str, object], scope_ids: list[str]) -> None:
        added = payload.get("claim_ids_add")
        removed = payload.get("claim_ids_remove")
        if not isinstance(added, list) or not isinstance(removed, list):
            raise ChangeConflict("claim ids are invalid")
        requested = [*added, *removed]
        self._match_scope(scope_ids, requested)
        if set(added).intersection(removed):
            raise ChangeConflict("claim cannot be both added and removed")
        baseline = read_json_object(self.root / "content_baseline.json")
        allowed = self._ids(baseline.get("claims"), "claim_id")
        if not set(requested).issubset(allowed):
            raise ChangeConflict("claim is not in the approved Gate 2 set")

    def _validate_voice(self, payload: Mapping[str, object]) -> None:
        approved = read_json_object(self._approved_script_path())
        current = approved.get("tts_settings")
        policy = approved.get("allowed_tts_settings")
        if not isinstance(current, Mapping):
            raise ChangeConflict("approved voice settings are missing")
        if not isinstance(policy, Mapping):
            policy = {
                "providers": [current.get("provider")],
                "speakers": [current.get("speaker", current.get("voice"))],
                "speed_min": current.get("speed", current.get("speed_ratio")),
                "speed_max": current.get("speed", current.get("speed_ratio")),
            }
        provider = payload.get("provider")
        speaker = payload.get("speaker")
        speed = payload.get("speed")
        providers = policy.get("providers")
        speakers = policy.get("speakers")
        lower = policy.get("speed_min")
        upper = policy.get("speed_max")
        if not isinstance(providers, list) or provider not in providers or not isinstance(speakers, list) or speaker not in speakers:
            raise ChangeConflict("voice provider or speaker is not allowlisted")
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not isinstance(lower, (int, float)) or isinstance(lower, bool) or not isinstance(upper, (int, float)) or isinstance(upper, bool) or not float(lower) <= float(speed) <= float(upper):
            raise ChangeConflict("voice speed is outside the approved range")

    def _validate_range(self, payload: Mapping[str, object]) -> None:
        fragment_id = payload.get("fragment_id")
        start = payload.get("start_seconds")
        end = payload.get("end_seconds")
        if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or not math.isfinite(float(start)) or not math.isfinite(float(end)) or not 0 <= float(start) < float(end):
            raise ChangeConflict("range is invalid")
        plan = read_json_object(self._fragment_plan_path())
        for row in plan.get("fragments", []):
            if isinstance(row, Mapping) and row.get("fragment_id") == fragment_id:
                broad = row.get("approved_broad_range")
                if isinstance(broad, Mapping):
                    lower, upper = broad.get("start_seconds"), broad.get("end_seconds")
                    if isinstance(lower, (int, float)) and not isinstance(lower, bool) and isinstance(upper, (int, float)) and not isinstance(upper, bool) and float(lower) <= float(start) < float(end) <= float(upper):
                        return
                break
        raise ChangeConflict("range exceeds the approved broad range")

    def _validate_material(self, payload: Mapping[str, object]) -> None:
        fragment_id = payload.get("fragment_id")
        candidate_id = payload.get("candidate_id")
        source_sha256 = payload.get("source_sha256")
        if payload.get("overlay_decision") not in {"retain_source_text", "crop", "cover", "replace", "no_action"}:
            raise ChangeConflict("material overlay decision is invalid")
        matches = read_json_object(self.root / "matches.json")
        for row in matches.get("fragments", []):
            if not isinstance(row, Mapping) or row.get("fragment_id") != fragment_id:
                continue
            for candidate in row.get("candidates", []):
                if (isinstance(candidate, Mapping)
                        and candidate.get("candidate_id", candidate.get("asset_id")) == candidate_id
                        and candidate.get("source_sha256", candidate.get("sha256")) == source_sha256):
                    return
        raise ChangeConflict("material candidate or source hash is not allowlisted")

    def _validate_rerecord(self, payload: Mapping[str, object], scope_ids: list[str]) -> None:
        fragment_ids = payload.get("fragment_ids")
        if not isinstance(fragment_ids, list):
            raise ChangeConflict("rerecord fragment ids are invalid")
        self._match_scope(scope_ids, fragment_ids)
        approved = read_json_object(self._approved_script_path())
        rows = approved.get("lines")
        if not isinstance(rows, list):
            raise ChangeConflict("approved script lines are missing")
        selected: dict[str, list[str]] = {item: [] for item in fragment_ids if isinstance(item, str)}
        for row in rows:
            if isinstance(row, Mapping) and row.get("fragment_id") in selected and isinstance(row.get("text"), str):
                selected[str(row["fragment_id"])].append(str(row["text"]))
        if any(not texts for texts in selected.values()):
            raise ChangeConflict("rerecord fragment is not in the approved script")
        approved_text = "\n".join(text for fragment_id in fragment_ids for text in selected[str(fragment_id)])
        if hashlib.sha256(approved_text.encode("utf-8")).hexdigest() != payload.get("approved_text_sha256"):
            raise ChangeConflict("rerecord approved text hash does not match")

    def _validate_boundary(self, payload: Mapping[str, object], scope_ids: list[str]) -> None:
        boundary_id = payload.get("boundary_id")
        self._match_scope(scope_ids, [boundary_id])
        report = read_json_object(self.root / "proxy_boundary_report.json")
        rows = report.get("boundary_frames")
        if not isinstance(rows, list):
            raise ChangeConflict("boundary report is invalid")
        allowed: set[str] = set()
        for index, row in enumerate(rows, 1):
            if not isinstance(row, Mapping):
                continue
            explicit = row.get("boundary_id")
            allowed.add(str(explicit) if isinstance(explicit, str) and explicit else f"b{index:02d}")
        if boundary_id not in allowed:
            raise ChangeConflict("boundary is not allowlisted")

    def _validate_structural(self, payload: Mapping[str, object], scope_ids: list[str]) -> None:
        affected = payload.get("affected_ids")
        if not isinstance(affected, list):
            raise ChangeConflict("structural affected ids are invalid")
        self._match_scope(scope_ids, affected)
        baseline = read_json_object(self.root / "content_baseline.json")
        allowed = self._ids(baseline.get("fragments"), "fragment_id")
        if not set(affected).issubset(allowed):
            raise ChangeConflict("structural fragment is not allowlisted")

    def _validate_script_candidate_select(self, payload: Mapping[str, object], scope_ids: list[str]) -> None:
        candidate_id = payload.get("script_candidate_id")
        expected_hash = payload.get("script_candidates_sha256")
        self._match_scope(scope_ids, [candidate_id])
        candidates_path = self.root / "script_candidates.json"
        if not candidates_path.is_file() or candidates_path.is_symlink():
            raise ChangeConflict("script candidates artifact is missing")
        if _file_sha256(candidates_path) != expected_hash:
            raise ChangeConflict("script candidates hash is stale")
        candidates = read_json_object(candidates_path).get("candidates")
        if not isinstance(candidates, list):
            raise ChangeConflict("script candidates artifact is invalid")
        if not any(isinstance(row, Mapping) and row.get("script_candidate_id") == candidate_id for row in candidates):
            raise ChangeConflict("script candidate is not allowlisted")
        report = read_json_object(self.root / "script_candidate_validation_report.json")
        validated = report.get("candidates")
        if not isinstance(validated, list) or not any(isinstance(row, Mapping) and row.get("script_candidate_id") == candidate_id and row.get("status") == "passed" for row in validated):
            raise ChangeConflict("script candidate must be passed")

    @staticmethod
    def _match_scope(scope_ids: list[str], payload_ids: object) -> None:
        if not isinstance(payload_ids, list) or any(not isinstance(item, str) or not item for item in payload_ids) or set(scope_ids) != set(payload_ids):
            raise ChangeConflict("scope ids do not match the payload")

    def _approved_script_path(self) -> Path:
        state = read_json_object(self.root / "pipeline_state.json")
        artifact = state.get("artifacts", {}).get("approved_production_script")
        if isinstance(artifact, Mapping) and isinstance(artifact.get("path"), str):
            candidate = (self.root / artifact["path"]).resolve(strict=True)
            if self.root in candidate.parents and not candidate.is_symlink():
                return candidate
        return self.root / "approved_production_script.json"

    def _fragment_plan_path(self) -> Path:
        state = read_json_object(self.root / "pipeline_state.json")
        candidates: list[Path] = []
        for artifact in state.get("artifacts", {}).values():
            if not isinstance(artifact, Mapping) or not isinstance(artifact.get("path"), str):
                continue
            relative = str(artifact["path"])
            if relative.startswith("versions/fragment_plan/") and relative.endswith("/fragment_plan.json"):
                candidate = (self.root / relative).resolve(strict=True)
                if self.root in candidate.parents and not candidate.is_symlink():
                    candidates.append(candidate)
        if candidates:
            return max(candidates, key=lambda path: path.parent.name)
        return self.root / "fragment_plan.json"

    @staticmethod
    def _ids(rows: object, key: str) -> set[str]:
        if not isinstance(rows, list):
            return set()
        return {str(row[key]) for row in rows if isinstance(row, Mapping) and isinstance(row.get(key), str) and row.get(key)}


class ChangeImpactAnalyzer:
    """Compute a deterministic, read-only impact projection for one request."""

    def __init__(self, task_root: Path, *, actor: str, role: str = "operator") -> None:
        self.root = Path(task_root).resolve(strict=True)
        self.actor = actor
        self.role = role
        self.storage = TaskStorage(self.root)
        self.validator = _ChangeValidator(self.root, actor=actor, role=role)

    def preview(self, *, session_id: str, gate_id: str, request: Mapping[str, object]) -> dict[str, Any]:
        preview = self._preview(session_id=session_id, gate_id=gate_id, request=request)
        self.storage.append_event(
            {
                "event_type": "review.change_previewed",
                "session_id": session_id,
                "run_id": preview["run_id"],
                "gate_id": gate_id,
                "actor": self.actor,
                "preview_hash": preview["preview_hash"],
                "change_type": preview["change_type"],
            },
            state_revision=int(preview["state_revision"]),
        )
        return preview

    def _preview(self, *, session_id: str, gate_id: str, request: Mapping[str, object]) -> dict[str, Any]:
        normalized, identity = self.validator.validate(session_id, gate_id, request)
        impact = copy.deepcopy(_IMPACTS[str(normalized["change_type"])])
        package = read_json_object(self.root / "gate_review_packages" / f"{gate_id}.json")
        estimate = self._estimate(
            tuple(impact["stale_stages"]),
            policy_version=package.get("policy_version"),
            runtime_profile=package.get("runtime_profile"),
        )
        preview: dict[str, Any] = {
            "run_id": identity["run_id"],
            "gate_id": gate_id,
            "review_package_hash": identity["review_package_hash"],
            "state_revision": identity["state_revision"],
            "session_id": session_id,
            "actor": self.actor,
            "change_type": normalized["change_type"],
            "normalized_request": normalized,
            **impact,
            "estimated_machine_seconds": estimate,
        }
        preview["preview_hash"] = _sha256(preview)
        return preview

    def _estimate(self, stages: tuple[str, ...], *, policy_version: object, runtime_profile: object) -> dict[str, object]:
        values: list[float] = []
        for row in self.storage.read_metrics():
            if row.get("execution_stage_id") not in stages or row.get("status") != "succeeded":
                continue
            if isinstance(policy_version, str) and row.get("policy_version") != policy_version:
                continue
            if isinstance(runtime_profile, str) and row.get("runtime_profile") != runtime_profile:
                continue
            seconds = row.get("machine_seconds", row.get("wall_seconds"))
            if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and math.isfinite(float(seconds)) and float(seconds) >= 0:
                values.append(float(seconds))
        values = values[-20:]
        if len(values) < 3:
            return {"measurement_status": "not_measured", "reason": "fewer_than_three_comparable_samples", "sample_count": len(values), "p50": None, "p90": None}
        ordered = sorted(values)
        p90_index = max(0, math.ceil(0.9 * len(ordered)) - 1)
        return {"measurement_status": "measured", "sample_count": len(values), "p50": statistics.median(ordered), "p90": ordered[p90_index]}


class ChangeService:
    """Commit one confirmed change request and a durable pending recovery job."""

    def __init__(self, task_root: Path, *, actor: str, role: str = "operator") -> None:
        self.root = Path(task_root).resolve(strict=True)
        self.actor = actor
        self.role = role
        self.storage = TaskStorage(self.root)
        self.analyzer = ChangeImpactAnalyzer(self.root, actor=actor, role=role)

    def apply(
        self,
        *,
        session_id: str,
        gate_id: str,
        request: Mapping[str, object],
        preview_hash: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ChangeConflict("idempotency key is required")
        payload_digest = _sha256({"session_id": session_id, "gate_id": gate_id, "request": request, "preview_hash": preview_hash})
        ledger = self._ledger_path(idempotency_key)
        if ledger.exists():
            existing = read_json_object(ledger)
            if existing.get("payload_sha256") != payload_digest:
                raise ChangeConflict("idempotency conflict")
            result = existing.get("result")
            if not isinstance(result, Mapping):
                raise ChangeConflict("idempotency ledger is invalid")
            return dict(result)

        preview = self.analyzer._preview(session_id=session_id, gate_id=gate_id, request=request)
        if not isinstance(preview_hash, str) or preview_hash != preview["preview_hash"]:
            raise ChangeConflict("preview is stale")
        change_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        transaction_id = f"change-{change_id}"
        request_path = self.root / "change_requests" / f"{change_id}.json"
        job_path = self.root / "workbench" / "jobs" / f"{job_id}.json"
        override_path = self.root / "workbench" / "change_overrides" / f"{change_id}.json"
        staged = self.root / ".staging" / transaction_id
        staged.mkdir(parents=True, exist_ok=False)
        request_record = {
            "change_request_id": change_id,
            "run_id": preview["run_id"],
            "gate_id": gate_id,
            "review_package_hash": preview["review_package_hash"],
            "state_revision": preview["state_revision"],
            "session_id": session_id,
            "actor": self.actor,
            "created_at": _now(),
            "request": preview["normalized_request"],
            "impact": {key: value for key, value in preview.items() if key not in {"normalized_request"}},
            "status": "applied",
        }
        job_record = {
            "job_id": job_id,
            "run_id": preview["run_id"],
            "change_request_id": change_id,
            "earliest_affected_gate": preview["earliest_affected_gate"],
            "status": "pending",
            "attempt_count": 0,
            "session_id": session_id,
            "gate_id": gate_id,
            "stale_gates": preview["stale_gates"],
            "stale_stages": preview["stale_stages"],
            "change_override_path": override_path.relative_to(self.root).as_posix(),
            "created_at": _now(),
            "updated_at": _now(),
        }
        override_record = {
            "change_request_id": change_id,
            "run_id": preview["run_id"],
            "change_type": preview["change_type"],
            "request": preview["normalized_request"],
            "producer": {"service": "ChangeService", "actor": self.actor},
            "created_at": _now(),
            "lifecycle_status": "awaiting_materialization",
        }
        staged_request = staged / "change_request.json"
        staged_job = staged / "job.json"
        staged_override = staged / "change_override.json"
        atomic_write_json(staged_request, request_record)
        atomic_write_json(staged_job, job_record)
        atomic_write_json(staged_override, override_record)

        current = self.storage.read_state()
        expected_revision = int(preview["state_revision"])
        if current.get("state_revision") != expected_revision:
            raise ChangeConflict("state revision conflict")
        state_changes = self._state_changes(current, preview)
        result = {
            "change_request_id": change_id,
            "change_request_path": str(request_path),
            "change_override_path": str(override_path),
            "job_id": job_id,
            "job_path": str(job_path),
            "state_revision": expected_revision + 1,
            "status": "pending",
        }
        staged_ledger = staged / "idempotency.json"
        atomic_write_json(staged_ledger, {"idempotency_key": idempotency_key, "payload_sha256": payload_digest, "result": result})
        manager = TransactionManager(self.storage)
        try:
            manager.prepare(
                transaction_id=transaction_id,
                expected_revision=expected_revision,
                state_changes=state_changes,
                event={
                    "event_type": "change.applied",
                    "run_id": preview["run_id"],
                    "gate_id": gate_id,
                    "session_id": session_id,
                    "actor": self.actor,
                    "change_request_id": change_id,
                    "job_id": job_id,
                    "preview_hash": preview_hash,
                },
                promotions=(
                    ArtifactPromotion(staged_path=staged_request, final_path=request_path),
                    ArtifactPromotion(staged_path=staged_job, final_path=job_path),
                    ArtifactPromotion(staged_path=staged_override, final_path=override_path),
                    ArtifactPromotion(staged_path=staged_ledger, final_path=ledger),
                ),
            )
            manager.commit(transaction_id)
        except RevisionConflict as error:
            manager.reconcile(transaction_id)
            raise ChangeConflict("state revision conflict") from error
        except BaseException:
            record_path = self.root / ".transactions" / f"{transaction_id}.json"
            if record_path.is_file():
                manager.reconcile(transaction_id)
            raise

        return result

    def _state_changes(self, state: Mapping[str, object], preview: Mapping[str, object]) -> dict[str, object]:
        gates = dict(state.get("gate_status", {}))
        for gate_id in preview["stale_gates"]:
            if gate_id in gates:
                gates[gate_id] = "stale"
        gates["gate3"] = self._aggregate(gates, "gate3_material_selection", "gate3_evidence_closure")
        gates["gate4"] = self._aggregate(gates, "gate4_pre_generation", "gate4_post_generation")
        stages = dict(state.get("stage_status", {}))
        for stage_id in preview["stale_stages"]:
            if stage_id in stages:
                current = stages[stage_id]
                if isinstance(current, Mapping):
                    stages[stage_id] = {**dict(current), "status": "stale"}
                else:
                    stages[stage_id] = "stale"
        return {"gate_status": gates, "stage_status": stages}

    @staticmethod
    def _aggregate(gates: Mapping[str, object], first: str, second: str) -> str:
        statuses = {gates.get(first), gates.get(second)}
        if "stale" in statuses:
            return "stale"
        if statuses == {"approved"}:
            return "approved"
        if "rejected" in statuses:
            return "rejected"
        if "blocked" in statuses:
            return "blocked"
        if "awaiting_user" in statuses:
            return "awaiting_user"
        return "not_ready"

    def _ledger_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / "workbench" / "change_idempotency" / f"{digest}.json"


class WorkbenchOrchestrator:
    """Resume only an explicitly registered frozen G-B side after a change."""

    def __init__(self, workspace_root: Path, *, actor: str, runner_factory: object | None = None) -> None:
        self.workspace = Path(workspace_root).resolve(strict=True)
        if not isinstance(actor, str) or not actor.strip():
            raise ChangeConflict("actor is required")
        self.actor = actor.strip()
        self.registry = RunRegistry(self.workspace)
        self.runner_factory = runner_factory or self._real_runner

    def resume_job(self, *, run_id: str, job_id: str) -> dict[str, Any]:
        try:
            task = self.registry.resolve(run_id)
        except RunRegistryError as error:
            raise ChangeConflict(str(error)) from error
        if not isinstance(job_id, str) or not job_id or Path(job_id).name != job_id:
            raise ChangeConflict("job id is invalid")
        job_path = task / "workbench" / "jobs" / f"{job_id}.json"
        if job_path.is_symlink() or not job_path.is_file():
            raise ChangeConflict("job is unknown")
        job = read_json_object(job_path)
        if job.get("job_id") != job_id or job.get("run_id") != run_id:
            raise ChangeConflict("job identity mismatch")
        if job.get("status") == "completed":
            result = job.get("result")
            if not isinstance(result, Mapping):
                raise ChangeConflict("completed job result is invalid")
            return dict(result)
        if job.get("status") == "running":
            raise ChangeConflict("job is already running")
        override_relative = job.get("change_override_path")
        if not isinstance(override_relative, str):
            raise ChangeConflict("job change override is missing")
        override_path = (task / override_relative).resolve(strict=True)
        if task not in override_path.parents or override_path.is_symlink() or not override_path.is_file():
            raise ChangeConflict("job change override is unsafe")
        override = read_json_object(override_path)
        change_type = override.get("change_type")
        if change_type in {"claim_scope", "structural"}:
            pending = {
                **job,
                "status": "awaiting_gate2_revision",
                "updated_at": _now(),
                "retry_command": f"workbench-resume-change --run-id {run_id} --job-id {job_id}",
            }
            atomic_write_json(job_path, pending)
            return {"job_id": job_id, "run_id": run_id, "status": "awaiting_gate2_revision"}

        store = TaskStorage(task)
        state = store.read_state()
        if state.get("execution_mode") != "track-b-production" or state.get("run_id") != run_id:
            raise ChangeConflict("job task is not a Track-B run")
        running = {
            **job,
            "status": "running",
            "attempt_count": int(job.get("attempt_count", 0)) + 1,
            "updated_at": _now(),
        }
        atomic_write_json(job_path, running)
        try:
            self._materialize_override(task, override)
            self._prepare_resume(store, running)
            factory = self.runner_factory
            if not callable(factory):
                raise ChangeConflict("runner factory is invalid")
            runner = factory(task)
            result_status = "succeeded"
            for _ in range(64):
                result = runner.run(resume=True)
                result_status = str(getattr(result, "status", "unknown"))
                if result_status == "awaiting_user":
                    break
                if result_status != "succeeded":
                    raise StorageError(f"runner returned unexpected status: {result_status}")
                current = store.read_state()
                if not any(value in {"not_started", "failed"} for value in current.get("stage_status", {}).values()):
                    break
            else:
                raise StorageError("change resume exceeded the bounded stage limit")
        except BaseException as error:
            failed = {
                **running,
                "status": "failed",
                "updated_at": _now(),
                "last_error": str(error),
                "retry_command": f"workbench-resume-change --run-id {run_id} --job-id {job_id}",
            }
            atomic_write_json(job_path, failed)
            raise

        completed_result = {
            "job_id": job_id,
            "run_id": run_id,
            "status": "completed",
            "runner_status": result_status,
            "state_revision": int(store.read_state()["state_revision"]),
        }
        completed = {**running, "status": "completed", "updated_at": _now(), "completed_at": _now(), "result": completed_result}
        atomic_write_json(job_path, completed)
        current_revision = int(store.read_state()["state_revision"])
        store.append_event(
            {
                "event_type": "review.rework_completed",
                "session_id": job.get("session_id"),
                "run_id": run_id,
                "gate_id": job.get("gate_id"),
                "actor": self.actor,
                "job_id": job_id,
                "change_request_id": job.get("change_request_id"),
            },
            state_revision=current_revision,
        )
        return completed_result

    @staticmethod
    def _materialize_override(task: Path, override: Mapping[str, object]) -> None:
        request = override.get("request")
        if not isinstance(request, Mapping) or not isinstance(request.get("payload"), Mapping):
            raise ChangeConflict("change override request is invalid")
        change_type = override.get("change_type")
        payload = dict(request["payload"])
        change_id = override.get("change_request_id")
        if not isinstance(change_id, str) or not change_id:
            raise ChangeConflict("change override id is invalid")
        version_dir = task / "workbench" / "materialized_changes" / change_id
        version_dir.mkdir(parents=True, exist_ok=True)

        if change_type in {"material", "range"}:
            handoff_path = task / "stage_inputs" / "build-material-selection-package.json"
            if handoff_path.is_symlink() or not handoff_path.is_file():
                raise ChangeConflict("material selection stage input is missing")
            handoff = read_json_object(handoff_path)
            stage_payload = handoff.get("payload")
            if not isinstance(stage_payload, Mapping):
                raise ChangeConflict("material selection stage payload is invalid")
            updated_payload = copy.deepcopy(dict(stage_payload))
            fragment_id = str(payload["fragment_id"])
            if change_type == "range":
                ranges = dict(updated_payload.get("range_overrides", {}))
                ranges[fragment_id] = {
                    "start_seconds": payload["start_seconds"],
                    "end_seconds": payload["end_seconds"],
                }
                updated_payload["range_overrides"] = ranges
            else:
                candidates = dict(updated_payload.get("candidate_overrides", {}))
                candidates[fragment_id] = {
                    "candidate_id": payload["candidate_id"],
                    "source_sha256": payload["source_sha256"],
                }
                updated_payload["candidate_overrides"] = candidates
                overlays = dict(updated_payload.get("overlay_decisions", {}))
                overlays[fragment_id] = payload["overlay_decision"]
                updated_payload["overlay_decisions"] = overlays
            updated = {
                **handoff,
                "producer": {"service": "WorkbenchOrchestrator", "change_request_id": change_id},
                "created_at": _now(),
                "lifecycle_status": "draft",
                "payload": updated_payload,
            }
            WorkbenchOrchestrator._replace_validated_stage_input(
                task=task,
                path=handoff_path,
                before=handoff,
                after=updated,
                version_dir=version_dir,
            )
            return

        if change_type == "copy":
            candidate_path = task / "production_script_candidate.json"
            candidate = read_json_object(candidate_path)
            lines = candidate.get("lines")
            text_by_id = payload.get("text_by_id")
            if not isinstance(lines, list) or not isinstance(text_by_id, Mapping):
                raise ChangeConflict("copy materialization input is invalid")
            updated_lines = [
                {**dict(row), "text": text_by_id.get(row.get("line_id"), row.get("text"))}
                if isinstance(row, Mapping)
                else row
                for row in lines
            ]
            atomic_write_json(version_dir / "before-production-script-candidate.json", candidate)
            updated = {**candidate, "lines": updated_lines, "supersedes_change_request_id": change_id}
            atomic_write_json(version_dir / "production-script-candidate.json", updated)
            atomic_write_json(candidate_path, updated)
            return

        if change_type == "script_candidate_select":
            candidates = read_json_object(task / "script_candidates.json").get("candidates")
            candidate_id = payload.get("script_candidate_id")
            if not isinstance(candidates, list) or not isinstance(candidate_id, str):
                raise ChangeConflict("script candidate materialization input is invalid")
            selected = next(
                (row for row in candidates if isinstance(row, Mapping) and row.get("script_candidate_id") == candidate_id),
                None,
            )
            if not isinstance(selected, Mapping):
                raise ChangeConflict("selected script candidate is missing")
            validation = read_json_object(task / "script_candidate_validation_report.json").get("candidates")
            if not isinstance(validation, list) or not any(
                isinstance(row, Mapping) and row.get("script_candidate_id") == candidate_id and row.get("status") == "passed"
                for row in validation
            ):
                raise ChangeConflict("selected script candidate is not passed")
            candidate_path = task / "production_script_candidate.json"
            before = read_json_object(candidate_path) if candidate_path.is_file() else {}
            selected_value = dict(selected)
            if isinstance(before, Mapping):
                selected_value = {
                    **dict(before),
                    **selected_value,
                    "selected_script_candidate_id": candidate_id,
                    "supersedes_change_request_id": change_id,
                }
            atomic_write_json(version_dir / "before-production-script-candidate.json", before)
            atomic_write_json(version_dir / "production-script-candidate.json", selected_value)
            atomic_write_json(candidate_path, selected_value)
            WorkbenchOrchestrator._write_change_stage_input(
                task=task,
                stage_id="select-script-candidate",
                payload={"script_candidate_id": candidate_id},
                change_id=change_id,
                version_dir=version_dir,
            )
            return

        if change_type == "voice":
            WorkbenchOrchestrator._write_change_stage_input(
                task=task,
                stage_id="voice-preflight",
                payload=payload,
                change_id=change_id,
                version_dir=version_dir,
            )
            return

        if change_type == "rerecord":
            WorkbenchOrchestrator._write_change_stage_input(
                task=task,
                stage_id="generate-voice",
                payload={"fragment_ids":payload["fragment_ids"],"approved_text_sha256":payload["approved_text_sha256"]},
                change_id=change_id,
                version_dir=version_dir,
            )
            return

        if change_type == "boundary":
            WorkbenchOrchestrator._write_change_stage_input(
                task=task,
                stage_id="render-proxy",
                payload=payload,
                change_id=change_id,
                version_dir=version_dir,
            )
            return

        atomic_write_json(
            version_dir / "runtime-change-input.json",
            {"change_request_id": change_id, "change_type": change_type, "payload": payload},
        )

    @staticmethod
    def _write_change_stage_input(
        *,
        task: Path,
        stage_id: str,
        payload: Mapping[str, object],
        change_id: str,
        version_dir: Path,
    ) -> None:
        path = task / "stage_inputs" / f"{stage_id}.json"
        before = read_json_object(path) if path.is_file() and not path.is_symlink() else None
        value = {
            "artifact_type":"stage_input",
            "schema_id":"urn:capcut:remix-reference-video:artifact:stage-input",
            "schema_version":"1.0.0",
            "contract_version":"2.0.0-alpha.1",
            "skill_version":"2.0.0-alpha.1",
            "stage_id":stage_id,
            "producer":{"service":"WorkbenchOrchestrator","change_request_id":change_id},
            "created_at":_now(),
            "lifecycle_status":"draft",
            "input_hashes":{},
            "payload":dict(payload),
        }
        if before is not None:
            merged_payload = dict(before.get("payload", {})) if isinstance(before.get("payload"), Mapping) else {}
            merged_payload.update(payload)
            value = {**before, **value, "payload":merged_payload}
            WorkbenchOrchestrator._replace_validated_stage_input(task=task, path=path, before=before, after=value, version_dir=version_dir)
            return
        atomic_write_json(version_dir / path.name, value)
        atomic_write_json(path, value)
        validation = StageInputValidator(task).validate(path, expected_stage_id=stage_id)
        if not validation.valid:
            path.unlink(missing_ok=True)
            raise ChangeConflict("materialized stage input is invalid: " + "; ".join(validation.errors))

    @staticmethod
    def _replace_validated_stage_input(
        *,
        task: Path,
        path: Path,
        before: Mapping[str, object],
        after: Mapping[str, object],
        version_dir: Path,
    ) -> None:
        before_path = version_dir / f"before-{path.name}"
        after_path = version_dir / path.name
        if not before_path.exists():
            atomic_write_json(before_path, dict(before))
        atomic_write_json(after_path, dict(after))
        atomic_write_json(path, dict(after))
        validation = StageInputValidator(task).validate(path, expected_stage_id=path.stem)
        if not validation.valid:
            atomic_write_json(path, dict(before))
            raise ChangeConflict("materialized stage input is invalid: " + "; ".join(validation.errors))

    @staticmethod
    def _prepare_resume(store: TaskStorage, job: Mapping[str, object]) -> None:
        expected = int(store.read_state()["state_revision"])

        def transform(state: dict[str, Any]) -> dict[str, Any]:
            gates = dict(state.get("gate_status", {}))
            for gate_id in job.get("stale_gates", []):
                if gate_id in gates:
                    gates[str(gate_id)] = "not_ready"
            stages = dict(state.get("stage_status", {}))
            for stage_id in job.get("stale_stages", []):
                if stage_id in stages:
                    stages[str(stage_id)] = "not_started"
            return {**state, "gate_status": gates, "stage_status": stages, "active_command": None}

        store.update_state(transform, expected_revision=expected)

    @staticmethod
    def _real_runner(task: Path) -> object:
        from .production_runtime import ProductionRuntimeConfig, build_real_registry
        from .runner import ProductionRunner

        config = ProductionRuntimeConfig.from_file(task / "production_runtime_config.json")
        registry = build_real_registry(
            task_root=task,
            reference_path=config.reference_path,
            asset_root=config.asset_root,
            brief_path=config.brief_path,
            asset_profiles_path=config.asset_profiles_path,
            cache_path=config.cache_path,
            doubao_client_script=config.doubao_client_script,
            python_executable=config.python_executable,
            archive_root=config.archive_root,
        )
        return ProductionRunner.from_registry(task, registry)


__all__ = ["ChangeConflict", "ChangeImpactAnalyzer", "ChangeService", "WorkbenchOrchestrator"]
