"""Immutable-input, owner-evaluated creative baseline comparisons."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .storage import read_json_object


class CreativeBaselineError(ValueError):
    """Raised when a baseline is not comparable under the creative protocol."""


_BASELINE_V0_RUN_ID = "gb-cold-1786890259"
_RUBRIC_FIELDS = (
    "first_three_seconds",
    "script_coherence",
    "visual_consistency",
    "highlights",
    "viewing_experience",
)
_RUBRIC_RANK = {"low": 0, "ordinary": 1, "high": 2}
_ALLOWED_DELTAS = (
    "selected_decomposition",
    "selected_remix_strategy",
    "script",
    "material_selection_and_range",
    "timeline",
    "final_video",
)


class CreativeBaselineComparison:
    """Build and evaluate the §15 comparison record without owning approvals."""

    def register_baseline_v0(self, task_root: Path, *, video_version_id: str) -> dict[str, Any]:
        facts = self._facts(task_root)
        if facts["run_id"] != _BASELINE_V0_RUN_ID:
            raise CreativeBaselineError(
                f"baseline_v0 must be cold run {_BASELINE_V0_RUN_ID}"
            )
        return {
            "baseline_id": "baseline_v0",
            "run_id": facts["run_id"],
            "video_version_id": self._nonempty(video_version_id, "video_version_id"),
            "frozen_input_sha256": facts["frozen_input_sha256"],
            "fixed_inputs": facts["fixed_inputs"],
            "baseline_evaluation_asymmetry": (
                "baseline_v0 has no creative diagnostic artifacts; its rubric values "
                "are direct owner observations."
            ),
        }

    def prepare(
        self,
        baseline_v0: Mapping[str, Any],
        v1_task_root: Path,
        *,
        video_version_id: str,
    ) -> dict[str, Any]:
        if baseline_v0.get("baseline_id") != "baseline_v0":
            raise CreativeBaselineError("baseline_v0 registration is required")
        v1 = self._facts(v1_task_root)
        if not v1["creative_contract"]:
            raise CreativeBaselineError("baseline_v1 must use creative_contract_v1")
        fixed_v0 = baseline_v0.get("fixed_inputs")
        if not isinstance(fixed_v0, Mapping) or dict(fixed_v0) != v1["fixed_inputs"]:
            raise CreativeBaselineError("baseline_v1 frozen business inputs do not match baseline_v0")
        comparison_id = self._digest({
            "baseline_v0": baseline_v0["run_id"],
            "baseline_v0_video": baseline_v0["video_version_id"],
            "baseline_v1": v1["run_id"],
            "baseline_v1_video": video_version_id,
            "fixed_inputs": fixed_v0,
        })[:24]
        return {
            "comparison_id": f"creative-comparison-{comparison_id}",
            "policy_version": "creative_baseline_comparison_v1",
            "ai_enhancement_enabled": False,
            "allowed_deltas": list(_ALLOWED_DELTAS),
            "fixed_inputs": dict(fixed_v0),
            "v0": {
                "run_id": baseline_v0["run_id"],
                "video_version_id": baseline_v0["video_version_id"],
                "evaluation_context_id": f"evaluation-v0-{comparison_id}",
                "comparison_id": f"creative-comparison-{comparison_id}",
            },
            "v1": {
                "run_id": v1["run_id"],
                "video_version_id": self._nonempty(video_version_id, "video_version_id"),
                "evaluation_context_id": f"evaluation-v1-{comparison_id}",
                "comparison_id": f"creative-comparison-{comparison_id}",
            },
            "rubric": {
                "scale": ["low", "ordinary", "high"],
                "dimensions": list(_RUBRIC_FIELDS),
                "requires_owner_evidence_timestamps": True,
            },
            "observational_metrics": ["effective_decision_seconds", "rework_rounds"],
        }

    def evaluate(
        self,
        prepared: Mapping[str, Any],
        *,
        v0_evaluation: Mapping[str, object],
        v1_evaluation: Mapping[str, object],
        v1_required_objectives_passed: bool,
        v1_claim_evidence_passed: bool,
        v0_l0_passed: bool,
        v1_l0_passed: bool,
        no_unapproved_inputs: bool,
    ) -> dict[str, Any]:
        if prepared.get("ai_enhancement_enabled") is not False:
            raise CreativeBaselineError("first creative baseline comparison requires AI enhancement off")
        self._validate_rubric(v0_evaluation, "v0")
        self._validate_rubric(v1_evaluation, "v1")
        failed: list[str] = []
        if not v0_l0_passed:
            failed.append("v0_l0_not_passed")
        if not v1_l0_passed:
            failed.append("v1_l0_not_passed")
        if not v1_required_objectives_passed:
            failed.append("v1_required_objectives_not_passed")
        if not v1_claim_evidence_passed:
            failed.append("v1_claim_evidence_not_passed")
        if not no_unapproved_inputs:
            failed.append("unapproved_fact_material_or_enhancement")
        for dimension in ("first_three_seconds", "script_coherence"):
            if _RUBRIC_RANK[str(v1_evaluation[dimension])] <= _RUBRIC_RANK[str(v0_evaluation[dimension])]:
                failed.append(f"{dimension}_not_strictly_improved")
        for dimension in ("visual_consistency", "highlights", "viewing_experience"):
            if _RUBRIC_RANK[str(v1_evaluation[dimension])] < _RUBRIC_RANK[str(v0_evaluation[dimension])]:
                failed.append(f"{dimension}_regressed")
        return {
            "comparison_id": prepared.get("comparison_id"),
            "policy_version": prepared.get("policy_version"),
            "status": "passed" if not failed else "blocked",
            "failed_checks": failed,
            "v0_evaluation": dict(v0_evaluation),
            "v1_evaluation": dict(v1_evaluation),
            "observational_only": list(prepared.get("observational_metrics", [])),
        }

    def _facts(self, task_root: Path) -> dict[str, Any]:
        root = Path(task_root).resolve(strict=True)
        state = read_json_object(root / "pipeline_state.json")
        snapshot_path = root / "g_b_frozen_input_snapshot.json"
        snapshot = read_json_object(snapshot_path)
        brief = read_json_object(root / "project_brief.json")
        run_id = self._nonempty(state.get("run_id"), "pipeline_state.run_id")
        fixed_inputs = {
            "reference_sha256": snapshot.get("reference_sha256"),
            "brief_sha256": snapshot.get("brief_sha256"),
            "asset_profiles_sha256": snapshot.get("asset_profiles_sha256"),
            "asset_snapshot": snapshot.get("asset_snapshot"),
            "claims": brief.get("approved_claims"),
            "forbidden_claims": brief.get("forbidden_claims"),
            "audience": brief.get("audience"),
            "platform": brief.get("platform"),
            "voice": brief.get("voice"),
            "output": brief.get("output"),
        }
        if any(value is None for value in fixed_inputs.values()):
            raise CreativeBaselineError("frozen comparison inputs are incomplete")
        return {
            "run_id": run_id,
            "frozen_input_sha256": self._file_sha256(snapshot_path),
            "fixed_inputs": fixed_inputs,
            "creative_contract": snapshot.get("creative_contract_version") == "creative_contract_v1",
        }

    @staticmethod
    def _nonempty(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise CreativeBaselineError(f"{field} is required")
        return value.strip()

    @staticmethod
    def _file_sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    @staticmethod
    def _digest(value: Mapping[str, object]) -> str:
        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _validate_rubric(value: Mapping[str, object], name: str) -> None:
        missing = [field for field in _RUBRIC_FIELDS if value.get(field) not in _RUBRIC_RANK]
        if missing:
            raise CreativeBaselineError(f"{name} rubric is incomplete or invalid: {', '.join(missing)}")
