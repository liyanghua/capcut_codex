"""Authoritative coverage and deterministic material matching."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


class RetrievalError(ValueError):
    """Raised when retrieval inputs or review decisions are invalid."""


_WEIGHTS = {
    "semantic": 0.30,
    "action": 0.20,
    "composition": 0.20,
    "color": 0.15,
    "lighting": 0.10,
    "technical": 0.05,
}
_OVERLAY_POLICIES = frozenset(
    {"retain_source_text", "crop", "cover", "replace", "no_action"}
)


class RetrievalAdapter:
    scoring_version = "retrieval-score-v1"

    def build_coverage(
        self,
        *,
        scope: str,
        content_baseline: Mapping[str, object],
        asset_profiles: Sequence[Mapping[str, object]],
        gate2_approved: bool,
    ) -> dict[str, object]:
        if scope not in {"precheck", "authoritative"}:
            raise RetrievalError("coverage scope is invalid")
        if scope == "authoritative" and not gate2_approved:
            raise RetrievalError("authoritative coverage requires current Gate 2 approval")
        fragments = self._fragments(content_baseline)
        rows = []
        for fragment in fragments:
            eligible = sum(
                self._qualify(fragment["requirements"], asset)[0]
                for asset in asset_profiles
            )
            rows.append(
                {
                    "fragment_id": fragment["fragment_id"],
                    "eligible_candidate_count": eligible,
                    "status": "covered" if eligible else "missing_material",
                }
            )
        return {
            "artifact_type": "coverage_precheck" if scope == "precheck" else "coverage_report",
            "scope": scope,
            "authority": "advisory_only" if scope == "precheck" else "gate2_bound",
            "rows": rows,
            "status": "blocked" if any(row["status"] == "missing_material" for row in rows) else "ready",
        }

    def match_assets(
        self,
        *,
        content_baseline: Mapping[str, object],
        asset_profiles: Sequence[Mapping[str, object]],
        gate2_approved: bool,
    ) -> dict[str, Any]:
        if not gate2_approved:
            raise RetrievalError("matching requires current Gate 2 approval")
        fragments = self._fragments(content_baseline)
        rows: list[dict[str, Any]] = []
        for fragment in fragments:
            candidates: list[dict[str, Any]] = []
            for asset in asset_profiles:
                eligible, reasons = self._qualify(fragment["requirements"], asset)
                score = self._score(asset) if eligible else min(self._score(asset), 0.59)
                if eligible:
                    candidates.append(
                        {
                            "asset_id": asset.get("asset_id"),
                            "source_id": asset.get("source_id"),
                            "source_path": asset.get("source_path"),
                            "sha256": asset.get("sha256"),
                            "media_type": asset.get("media_type"),
                            "perceptual_hash": asset.get("perceptual_hash"),
                            "confidence": score,
                            "score_components": dict(asset.get("scores", {})),
                            "qualification_reasons": reasons,
                            "overlay_detected": bool(asset.get("overlay_detected")),
                            "duration_seconds": asset.get("duration_seconds"),
                            "broad_ranges": list(asset.get("broad_ranges", [])),
                        }
                    )
            candidates.sort(key=lambda row: (-row["confidence"], str(row["asset_id"])))
            unique: list[dict[str, Any]] = []
            seen_sha: set[object] = set()
            seen_perceptual: set[object] = set()
            for candidate in candidates:
                if candidate["sha256"] in seen_sha or candidate["perceptual_hash"] in seen_perceptual:
                    continue
                seen_sha.add(candidate["sha256"])
                seen_perceptual.add(candidate["perceptual_hash"])
                unique.append(candidate)
            status = "matched" if unique and unique[0]["confidence"] >= 0.60 else "missing_material"
            rows.append(
                {
                    "fragment_id": fragment["fragment_id"],
                    "status": status,
                    "candidates": unique,
                    "selected_asset_id": None,
                }
            )
        self._schedule(rows)
        payload = {
            "scoring_version": self.scoring_version,
            "baseline": content_baseline,
            "assets": list(asset_profiles),
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "artifact_type": "matches",
            "scoring_version": self.scoring_version,
            "cache_fingerprint": fingerprint,
            "status": "blocked" if any(row["status"] == "missing_material" for row in rows) else "ready",
            "fragments": rows,
        }

    def build_candidate_review_package(
        self,
        *,
        matches: Mapping[str, object],
        overlay_decisions: Mapping[str, str],
    ) -> dict[str, object]:
        if matches.get("status") != "ready":
            raise RetrievalError("candidate package cannot include missing material")
        rows = matches.get("fragments")
        if not isinstance(rows, list):
            raise RetrievalError("matches fragments must be an array")
        selections: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise RetrievalError("match row is invalid")
            fragment_id = row.get("fragment_id")
            policy = overlay_decisions.get(str(fragment_id))
            if policy not in _OVERLAY_POLICIES:
                raise RetrievalError(f"invalid overlay policy for {fragment_id}")
            selected = next(
                (
                    candidate
                    for candidate in row.get("candidates", [])
                    if isinstance(candidate, Mapping)
                    and candidate.get("asset_id") == row.get("selected_asset_id")
                ),
                None,
            )
            if selected is None:
                raise RetrievalError(f"selected candidate is missing for {fragment_id}")
            ranges = selected.get("broad_ranges")
            if not isinstance(ranges, list) or not ranges or not isinstance(ranges[0], Mapping):
                raise RetrievalError(f"approved broad range is missing for {fragment_id}")
            source_path = str(selected.get("source_path", ""))
            media_type = selected.get("media_type")
            if media_type not in {"video", "image"}:
                media_type = (
                    "image"
                    if source_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                    else "video"
                )
            selections.append(
                {
                    "fragment_id": fragment_id,
                    "asset_id": selected["asset_id"],
                    "source_id": selected["source_id"],
                    "source_path": selected["source_path"],
                    "sha256": selected["sha256"],
                    "media_type": media_type,
                    "overlay_policy": policy,
                    "approved_broad_range": dict(ranges[0]),
                    "available_source_range": {
                        "start_seconds": 0.0,
                        "end_seconds": selected["duration_seconds"],
                    },
                }
            )
        return {
            "artifact_type": "material_selection_candidate",
            "gate_id": "gate3_material_selection",
            "scoring_version": self.scoring_version,
            "selections": selections,
            "lifecycle_status": "awaiting_user",
        }

    @staticmethod
    def _fragments(baseline: Mapping[str, object]) -> list[Mapping[str, object]]:
        if baseline.get("artifact_type") != "content_baseline":
            raise RetrievalError("content_baseline artifact is required")
        rows = baseline.get("fragments")
        if not isinstance(rows, list):
            raise RetrievalError("baseline fragments must be an array")
        for row in rows:
            if not isinstance(row, Mapping) or not isinstance(row.get("requirements"), Mapping):
                raise RetrievalError("fragment requirements are missing")
        return rows

    @staticmethod
    def _qualify(
        requirements: object, asset: Mapping[str, object]
    ) -> tuple[bool, list[str]]:
        if not isinstance(requirements, Mapping):
            return False, ["requirements_missing"]
        reasons: list[str] = []
        if asset.get("product_type") != requirements.get("product_type"):
            reasons.append("product_mismatch")
        semantic = set(asset.get("semantic_tags", []))
        if not set(requirements.get("required_semantics", [])) <= semantic:
            reasons.append("semantic_evidence_missing")
        if set(requirements.get("forbidden_semantics", [])).intersection(semantic):
            reasons.append("forbidden_semantics")
        if not set(requirements.get("required_actions", [])) <= set(asset.get("action_tags", [])):
            reasons.append("action_incomplete")
        if asset.get("media_type") not in requirements.get("allowed_media_types", []):
            reasons.append("media_type_ineligible")
        expected = requirements.get("expected_visual_seconds", 0)
        duration = asset.get("duration_seconds")
        if not isinstance(duration, (int, float)) or duration < float(expected):
            reasons.append("duration_insufficient")
        return not reasons, reasons

    @staticmethod
    def _score(asset: Mapping[str, object]) -> float:
        scores = asset.get("scores")
        if not isinstance(scores, Mapping):
            return 0.0
        total = 0.0
        for dimension, weight in _WEIGHTS.items():
            value = scores.get(dimension, 0)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise RetrievalError(f"invalid {dimension} score")
            total += float(value) * weight
        return round(total, 4)

    @staticmethod
    def _schedule(rows: list[dict[str, Any]]) -> None:
        selected_sources: list[object] = []
        for row in rows:
            if row["status"] != "matched":
                continue
            candidates = row["candidates"]
            selected = candidates[0]
            if len(selected_sources) >= 2 and selected_sources[-2:] == [selected["source_id"]] * 2:
                selected = next(
                    (item for item in candidates if item["source_id"] != selected["source_id"]),
                    selected,
                )
            row["selected_asset_id"] = selected["asset_id"]
            selected_sources.append(selected["source_id"])
