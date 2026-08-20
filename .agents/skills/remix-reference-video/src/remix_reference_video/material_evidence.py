"""Human-reviewed business evidence layered over immutable technical profiles."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .snapshot_schema_validator import SnapshotSchemaError, SnapshotSchemaValidator
from .storage import TaskStorage, atomic_write_json, read_json_object


_ENVELOPE = {
    "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
}
_SCORE_KEYS = ("semantic", "action", "composition", "color", "lighting", "technical")


class MaterialEvidenceError(ValueError):
    pass


class MaterialEvidenceService:
    """Persist current operator evidence and resume the paused creative run."""

    def __init__(
        self,
        task_root: Path,
        *,
        actor: str,
        role: str = "operator",
        runner_factory: object | None = None,
    ) -> None:
        self.root = Path(task_root).resolve(strict=True)
        if not actor.strip() or role not in {"operator", "owner"}:
            raise MaterialEvidenceError("current operator identity is invalid")
        self.actor = actor.strip()
        self.role = role
        self.store = TaskStorage(self.root)
        self.runner_factory = runner_factory or self._real_runner

    def submit(
        self,
        *,
        annotations: object,
        expected_requirements_sha256: str,
        expected_asset_profiles_sha256: str,
        request_id: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        if not isinstance(annotations, list) or not request_id.strip() or not idempotency_key.strip():
            raise MaterialEvidenceError("annotations, request_id and idempotency_key are required")
        requirements_path = self.root / "material_evidence_requirements.json"
        profiles_path = self.root / "asset_profiles.json"
        if (
            not requirements_path.is_file()
            or not profiles_path.is_file()
            or _file_sha256(requirements_path) != expected_requirements_sha256
            or _file_sha256(profiles_path) != expected_asset_profiles_sha256
        ):
            raise MaterialEvidenceError("material evidence inputs are stale")
        payload_hash = _digest({
            "annotations": annotations,
            "requirements_sha256": expected_requirements_sha256,
            "asset_profiles_sha256": expected_asset_profiles_sha256,
        })
        ledger_path = self.root / ".idempotency" / f"material-evidence-{hashlib.sha256(idempotency_key.encode()).hexdigest()}.json"
        if ledger_path.is_file():
            ledger = read_json_object(ledger_path)
            if ledger.get("payload_hash") != payload_hash:
                raise MaterialEvidenceError("idempotency key conflict")
            return dict(ledger["result"])
        state = self.store.read_state()
        if state.get("active_stage") != "collect-material-evidence" or not any(
            isinstance(row, Mapping) and row.get("category") == "manual_classification_required"
            for row in state.get("blockers", [])
        ):
            raise MaterialEvidenceError("run is not waiting for material evidence")
        profiles_artifact = read_json_object(profiles_path)
        profiles = profiles_artifact.get("asset_profiles")
        if not isinstance(profiles, list):
            raise MaterialEvidenceError("asset profiles are invalid")
        artifact = {
            **_ENVELOPE,
            "artifact_type": "material_evidence_annotations",
            "schema_id": "urn:capcut:remix-reference-video:artifact:material-evidence-annotations",
            "lifecycle_status": "ready",
            "input_hashes": {
                "asset_profiles.json": expected_asset_profiles_sha256,
                "material_evidence_requirements.json": expected_requirements_sha256,
            },
            "annotations": annotations,
        }
        try:
            SnapshotSchemaValidator().assert_valid(artifact, "material-evidence-annotations.schema.json")
        except SnapshotSchemaError as error:
            raise MaterialEvidenceError(f"material evidence schema validation failed: {error}") from None
        merge_material_evidence(profiles, artifact)
        staging = self.root / ".staging" / f"material-evidence-{uuid.uuid4()}"
        staged = staging / "material_evidence_annotations.json"
        atomic_write_json(staged, artifact)
        with self.store.invocation_lock():
            current = self.store.read_state()
            if current.get("state_revision") != state.get("state_revision"):
                raise MaterialEvidenceError("material evidence state is stale")
            final_path = self.root / "material_evidence_annotations.json"
            if final_path.exists():
                version = self.root / "versions" / "material_evidence_annotations" / f"r{current['state_revision']}.json"
                version.parent.mkdir(parents=True, exist_ok=True)
                final_path.replace(version)
            staged.replace(final_path)
            downstream = self._downstream_stage_ids()
            updated = self.store.update_state(
                lambda value: {
                    **value,
                    "active_stage": "build-material-evidence-requirements",
                    "active_command": None,
                    "blockers": [
                        row for row in value.get("blockers", [])
                        if not (isinstance(row, Mapping) and row.get("category") == "manual_classification_required")
                    ],
                    "stage_status": {
                        **value.get("stage_status", {}),
                        **{stage_id: "not_started" for stage_id in downstream if stage_id in value.get("stage_status", {})},
                    },
                    "cache_summary": {
                        key: row for key, row in value.get("cache_summary", {}).items() if key not in downstream
                    },
                },
                expected_revision=int(current["state_revision"]),
            )
            self.store.append_event(
                {
                    "event_type": "material_evidence.submitted", "actor": self.actor,
                    "role": self.role, "request_id": request_id,
                    "requirements_sha256": expected_requirements_sha256,
                },
                state_revision=int(updated["state_revision"]),
            )
        if staging.exists():
            staging.rmdir()
        runner = self.runner_factory(self.root)
        result = runner.run(resume=True)
        response = {
            "run_id": str(state.get("run_id", "")),
            "status": "submitted",
            "resume_status": str(getattr(result, "status", "unknown")),
            "annotation_sha256": _file_sha256(self.root / "material_evidence_annotations.json"),
        }
        atomic_write_json(ledger_path, {"payload_hash": payload_hash, "result": response})
        return response

    @staticmethod
    def _downstream_stage_ids() -> list[str]:
        from .orchestrator import creative_dag

        order = [node.node_id for node in creative_dag()]
        start = order.index("build-material-evidence-requirements")
        return order[start:]

    @staticmethod
    def _real_runner(task_root: Path) -> object:
        from .change_service import WorkbenchOrchestrator

        return WorkbenchOrchestrator._real_runner(task_root)


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def merge_material_evidence(
    technical_profiles: Sequence[Mapping[str, object]],
    annotations: Mapping[str, object] | None,
) -> dict[str, object]:
    profiles = [dict(row) for row in technical_profiles if isinstance(row, Mapping)]
    by_id = {row.get("asset_id"): row for row in profiles if isinstance(row.get("asset_id"), str)}
    if len(by_id) != len(profiles):
        raise MaterialEvidenceError("technical asset ids must be unique")
    if annotations is None:
        return {
            "profiles": [],
            "blockers": [
                {"category": "manual_classification_required", "asset_id": row["asset_id"]}
                for row in profiles
            ],
        }
    rows = annotations.get("annotations")
    if not isinstance(rows, list):
        raise MaterialEvidenceError("annotations must be an array")
    seen: set[str] = set()
    merged: list[dict[str, object]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise MaterialEvidenceError("annotation must be an object")
        asset_id = raw.get("asset_id")
        if not isinstance(asset_id, str) or asset_id not in by_id:
            raise MaterialEvidenceError("annotation asset is unknown")
        if asset_id in seen:
            raise MaterialEvidenceError("duplicate asset annotation")
        seen.add(asset_id)
        technical = by_id[asset_id]
        if raw.get("source_path") != technical.get("source_path") or raw.get("sha256") != technical.get("sha256"):
            raise MaterialEvidenceError("annotation source hash or path is stale")
        window = raw.get("evidence_window")
        if not isinstance(window, Mapping):
            raise MaterialEvidenceError("annotation evidence window is required")
        kind = window.get("kind")
        if kind == "frame":
            if not isinstance(window.get("frame_path"), str) or not str(window["frame_path"]).strip():
                raise MaterialEvidenceError("annotation evidence window is unreviewable")
            broad = {"start_seconds": 0.0, "end_seconds": 60.0}
        elif kind == "time_range":
            start, end = window.get("start_seconds"), window.get("end_seconds")
            duration = technical.get("duration_seconds")
            if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in (start, end)) or float(start) < 0 or float(end) <= float(start):
                raise MaterialEvidenceError("annotation evidence window is invalid")
            if isinstance(duration, (int, float)) and float(end) > float(duration):
                raise MaterialEvidenceError("annotation evidence window exceeds source duration")
            broad = {"start_seconds": float(start), "end_seconds": float(end)}
        else:
            raise MaterialEvidenceError("annotation evidence window kind is invalid")
        scores = raw.get("scores")
        if not isinstance(scores, Mapping) or any(
            isinstance(scores.get(key), bool) or not isinstance(scores.get(key), (int, float))
            or not 0 <= float(scores[key]) <= 1 for key in _SCORE_KEYS
        ):
            raise MaterialEvidenceError("annotation scores require a complete reviewed rubric")
        product_type = raw.get("product_type")
        semantics, actions = raw.get("semantic_tags"), raw.get("action_tags")
        if not isinstance(product_type, str) or not product_type or not isinstance(semantics, list) or not isinstance(actions, list):
            raise MaterialEvidenceError("annotation business evidence is incomplete")
        media_type = technical.get("media_type")
        merged.append({
            **technical,
            "source_id": str(technical.get("source_path")),
            "perceptual_hash": str(technical.get("sha256")),
            "product_type": product_type,
            "semantic_tags": list(semantics), "action_tags": list(actions),
            "scene_tags": list(raw.get("scene_tags", [])) if isinstance(raw.get("scene_tags", []), list) else [],
            "overlay_detected": raw.get("overlay_decision") != "none",
            "overlay_decision": raw.get("overlay_decision"),
            "scores": {key: float(scores[key]) for key in _SCORE_KEYS},
            "score_basis": raw.get("score_basis"),
            "duration_seconds": 60.0 if media_type == "image" else technical.get("duration_seconds"),
            "broad_ranges": [broad],
            "evidence_source": raw.get("evidence_source"),
            "evidence_window": dict(window),
        })
    blockers = [
        {"category": "manual_classification_required", "asset_id": row["asset_id"]}
        for row in profiles if row["asset_id"] not in seen
    ]
    return {"profiles": merged, "blockers": blockers}


def build_material_evidence_requirements(
    content_baseline: Mapping[str, object],
    technical_profiles: Sequence[Mapping[str, object]],
    annotations: Mapping[str, object] | None,
) -> dict[str, object]:
    fragments = content_baseline.get("fragments")
    if content_baseline.get("artifact_type") != "content_baseline" or not isinstance(fragments, list):
        raise MaterialEvidenceError("content baseline fragments are required")
    merged = merge_material_evidence(technical_profiles, annotations)
    annotated = merged["profiles"]
    rows: list[dict[str, object]] = []
    for fragment in fragments:
        if not isinstance(fragment, Mapping) or not isinstance(fragment.get("requirements"), Mapping):
            raise MaterialEvidenceError("fragment material requirements are required")
        requirements = fragment["requirements"]
        eligible_ids: list[str] = []
        for profile in annotated:
            reasons = []
            if profile.get("product_type") != requirements.get("product_type"):
                reasons.append("product_type")
            if not set(requirements.get("required_semantics", [])) <= set(profile.get("semantic_tags", [])):
                reasons.append("semantic_tags")
            if not set(requirements.get("required_actions", [])) <= set(profile.get("action_tags", [])):
                reasons.append("action_tags")
            if not reasons:
                eligible_ids.append(str(profile["asset_id"]))
        missing = [] if eligible_ids else ["product_type", "semantic_tags", "action_tags", "overlay_decision", "evidence_window"]
        rows.append({
            "fragment_id": fragment.get("fragment_id"), "missing_fields": missing,
            "eligible_asset_ids": eligible_ids,
            "candidate_assets": [
                {"asset_id": row.get("asset_id"), "source_path": row.get("source_path"), "sha256": row.get("sha256"), "media_type": row.get("media_type")}
                for row in technical_profiles
            ],
        })
    status = "manual_classification_required" if any(row["missing_fields"] for row in rows) else "ready"
    return {
        **_ENVELOPE, "artifact_type": "material_evidence_requirements",
        "schema_id": "urn:capcut:remix-reference-video:artifact:material-evidence-requirements",
        "lifecycle_status": "ready", "input_hashes": {
            "content_baseline.json": _digest(content_baseline), "asset_profiles.json": _digest(list(technical_profiles)),
            **({"material_evidence_annotations.json": _digest(annotations)} if annotations is not None else {}),
        },
        "status": status, "requirements": rows,
    }


__all__ = ["MaterialEvidenceError", "MaterialEvidenceService", "build_material_evidence_requirements", "merge_material_evidence"]
