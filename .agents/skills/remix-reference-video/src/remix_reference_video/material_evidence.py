"""Human-reviewed business evidence layered over immutable technical profiles."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence


_ENVELOPE = {
    "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
}
_SCORE_KEYS = ("semantic", "action", "composition", "color", "lighting", "technical")


class MaterialEvidenceError(ValueError):
    pass


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


__all__ = ["MaterialEvidenceError", "build_material_evidence_requirements", "merge_material_evidence"]
