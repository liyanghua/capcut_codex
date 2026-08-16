"""Gate 3 selection freezing, evidence closure, and stale projections."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..storage import read_json_object


class Gate3Error(ValueError):
    """Raised when Gate 3 inputs are stale or exceed their approval scope."""


class Gate3Adapter:
    implementation_version = "gate3-adapter-v1"

    def build_material_selection_package(
        self,
        *,
        candidate_path: Path,
        run_id: str,
        state_revision: int,
        created_at: str,
    ) -> dict[str, object]:
        path = self._input(candidate_path, "material_selection_candidate.json")
        candidate = read_json_object(path)
        if candidate.get("artifact_type") != "material_selection_candidate":
            raise Gate3Error("material selection candidate is required")
        if not isinstance(run_id, str) or not run_id:
            raise Gate3Error("run_id is required")
        if isinstance(state_revision, bool) or not isinstance(state_revision, int) or state_revision < 0:
            raise Gate3Error("state_revision must be nonnegative")
        return {
            "artifact_type": "gate_review_package",
            "schema_id": "urn:capcut:remix-reference-video:artifact:gate-review-package",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "gate_id": "gate3_material_selection",
            "run_id": run_id,
            "state_revision": state_revision,
            "created_at": created_at,
            "input_hashes": {"material_selection_candidate.json": self._sha256(path)},
            "selections": candidate.get("selections", []),
        }

    def freeze_fragment_plan(
        self,
        *,
        candidate_path: Path,
        approval_record: Mapping[str, object],
    ) -> dict[str, object]:
        path = self._input(candidate_path, "material_selection_candidate.json")
        if (
            approval_record.get("gate_id") != "gate3_material_selection"
            or approval_record.get("decision") != "approved"
        ):
            raise Gate3Error("current material selection approval is required")
        hashes = approval_record.get("input_hashes")
        if not isinstance(hashes, Mapping) or hashes.get(path.name) != self._sha256(path):
            raise Gate3Error("approval does not bind current candidate hash")
        strategy = approval_record.get("strategy", {})
        if not isinstance(strategy, Mapping):
            raise Gate3Error("selection strategy must be an object")
        if any(
            key in {"request_omit", "request_merge", "request_restructure"} and value
            for key, value in strategy.items()
        ):
            raise Gate3Error("structural changes must return to Gate 2")
        overrides = strategy.get("range_overrides", {})
        if not isinstance(overrides, Mapping):
            raise Gate3Error("range_overrides must be an object")
        candidate = read_json_object(path)
        selections = candidate.get("selections")
        if not isinstance(selections, list) or not selections:
            raise Gate3Error("candidate selections are missing")
        fragments: list[dict[str, object]] = []
        for row in selections:
            if not isinstance(row, Mapping) or not isinstance(row.get("fragment_id"), str):
                raise Gate3Error("candidate selection is invalid")
            fragment_id = str(row["fragment_id"])
            source_path = str(row.get("source_path", ""))
            media_type = row.get("media_type")
            if media_type not in {"video", "image"}:
                media_type = (
                    "image"
                    if source_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                    else "video"
                )
            image = media_type == "image"
            if image:
                start = end = None
                duration_budget = None
            else:
                selected_range = overrides.get(fragment_id, row.get("approved_broad_range"))
                available = row.get("available_source_range")
                start, end = self._range(selected_range, f"{fragment_id} approved broad range")
                available_start, available_end = self._range(
                    available, f"{fragment_id} available source range"
                )
                if start < available_start or end > available_end:
                    raise Gate3Error(f"{fragment_id} exceeds available source range")
                duration_budget = round(end - start, 6)
            fragments.append(
                {
                    "fragment_id": fragment_id,
                    "asset_id": row.get("asset_id"),
                    "source_id": row.get("source_id"),
                    "source_path": row.get("source_path"),
                    "source_sha256": row.get("sha256"),
                    "media_type": media_type,
                    "overlay_policy": row.get("overlay_policy"),
                    "visual_duration_budget_seconds": duration_budget,
                    "approved_broad_range": {
                        "start_seconds": start,
                        "end_seconds": end,
                    },
                }
            )
        return {
            "artifact_type": "fragment_plan",
            "schema_id": "urn:capcut:remix-reference-video:artifact:fragment-plan",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "lifecycle_status": "approved",
            "selection_approval_id": approval_record.get("decision_id"),
            "input_hashes": {path.name: self._sha256(path)},
            "fragments": fragments,
        }

    def build_evidence_package(
        self,
        *,
        evidence_matrix_path: Path,
        run_id: str,
        state_revision: int,
        created_at: str,
    ) -> dict[str, object]:
        path = self._input(evidence_matrix_path, "script_evidence_matrix.json")
        matrix = read_json_object(path)
        if (
            matrix.get("artifact_type") != "script_evidence_matrix"
            or matrix.get("lifecycle_status") != "awaiting_user"
        ):
            raise Gate3Error("awaiting evidence matrix is required")
        if not isinstance(run_id, str) or not run_id:
            raise Gate3Error("run_id is required")
        if isinstance(state_revision, bool) or not isinstance(state_revision, int) or state_revision < 0:
            raise Gate3Error("state_revision must be nonnegative")
        return {
            "artifact_type": "gate_review_package",
            "schema_id": "urn:capcut:remix-reference-video:artifact:gate-review-package",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "gate_id": "gate3_evidence_closure",
            "run_id": run_id,
            "state_revision": state_revision,
            "created_at": created_at,
            "input_hashes": {path.name: self._sha256(path)},
        }

    def validate_script_evidence(
        self,
        *,
        content_baseline_path: Path,
        fragment_plan_path: Path,
        evidence_rows: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        baseline_path = self._input(content_baseline_path, "content_baseline.json")
        plan_path = self._input(fragment_plan_path, "fragment_plan.json")
        baseline = read_json_object(baseline_path)
        plan = read_json_object(plan_path)
        if baseline.get("artifact_type") != "content_baseline":
            raise Gate3Error("content baseline is required")
        if plan.get("artifact_type") != "fragment_plan" or plan.get("lifecycle_status") != "approved":
            raise Gate3Error("approved fragment plan is required")
        claim_ids = {
            row.get("claim_id")
            for row in baseline.get("claims", [])
            if isinstance(row, Mapping) and isinstance(row.get("claim_id"), str)
        }
        plan_ids = {
            row.get("fragment_id")
            for row in plan.get("fragments", [])
            if isinstance(row, Mapping)
        }
        by_fragment: dict[str, Mapping[str, object]] = {}
        for row in evidence_rows:
            fragment_id = row.get("fragment_id")
            if not isinstance(fragment_id, str) or fragment_id not in plan_ids:
                raise Gate3Error("evidence references unapproved fragment")
            claims = row.get("approved_claim_ids")
            if not isinstance(claims, list) or not set(claims) <= claim_ids:
                raise Gate3Error(f"{fragment_id} evidence exceeds claim boundary")
            if not str(row.get("closure_decision", "")).startswith("closed"):
                raise Gate3Error(f"{fragment_id} evidence is not closed")
            by_fragment[fragment_id] = row
        required = {
            row.get("fragment_id")
            for row in baseline.get("fragments", [])
            if isinstance(row, Mapping)
            and isinstance(row.get("narration"), str)
            and row["narration"].strip()
        }
        missing = sorted(str(item) for item in required - set(by_fragment))
        if missing:
            raise Gate3Error(f"missing evidence rows: {', '.join(missing)}")
        return {
            "artifact_type": "script_evidence_matrix",
            "schema_id": "urn:capcut:remix-reference-video:artifact:script-evidence-matrix",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "lifecycle_status": "awaiting_user",
            "input_hashes": {
                baseline_path.name: self._sha256(baseline_path),
                plan_path.name: self._sha256(plan_path),
            },
            "rows": [dict(row) for row in evidence_rows],
        }

    @staticmethod
    def summarize_gate3(gate_status: Mapping[str, object]) -> str:
        statuses = (
            gate_status.get("gate3_material_selection"),
            gate_status.get("gate3_evidence_closure"),
        )
        if statuses == ("approved", "approved"):
            return "approved"
        for status in ("stale", "blocked", "rejected"):
            if status in statuses:
                return status
        return "awaiting_user"

    @staticmethod
    def _range(value: object, field: str) -> tuple[float, float]:
        if not isinstance(value, Mapping):
            raise Gate3Error(f"{field} is missing")
        start, end = value.get("start_seconds"), value.get("end_seconds")
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or start < 0
            or end <= start
        ):
            raise Gate3Error(f"{field} is invalid")
        return float(start), float(end)

    @staticmethod
    def _input(path: Path, expected_name: str) -> Path:
        requested = Path(path)
        if requested.name != expected_name or requested.is_symlink():
            raise Gate3Error(f"input must be {expected_name}")
        return requested.resolve(strict=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()


def gate3_stale_projection(
    *,
    change_type: str,
    affected_asset_ids: set[str],
    selected_asset_ids: set[str],
) -> dict[str, object]:
    if change_type not in {"source_content", "overlay", "broad_range"}:
        return {"gate_status": {}, "reusable_asset_ids": sorted(selected_asset_ids)}
    gates = (
        "gate3_material_selection",
        "gate3_evidence_closure",
        "gate3",
        "gate4_pre_generation",
        "gate4_post_generation",
        "gate4",
        "gate5",
    )
    return {
        "gate_status": {gate: "stale" for gate in gates},
        "reusable_asset_ids": sorted(selected_asset_ids - affected_asset_ids),
    }
