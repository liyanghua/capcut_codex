"""Deterministic narrative coherence gate between Gate 3 evidence closure and script compilation.

The gate never invents narrative intent: roles and required actions come from the
Gate 2 frozen content baseline (`narrative_contract_v1`). Transitions are assigned
from the versioned `continuity_lexicon_v1` connector table and never add product
facts. A blocked or manual-review report prevents script compilation.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .storage import StorageError, read_json_object

NARRATIVE_CONTRACT_VERSION = "narrative_contract_v1"
CONTINUITY_LEXICON_VERSION = "continuity_lexicon_v1"

_ROLES = ("开场情境", "问题/需求", "产品出现", "功能证明", "使用结果", "收束")
_ACTIONS = ("show_context", "show_problem", "show_product", "demonstrate_feature", "show_result", "close")
_ROLE_TO_ACTION = {
    "开场情境": "show_context",
    "问题/需求": "show_problem",
    "产品出现": "show_product",
    "功能证明": "demonstrate_feature",
    "使用结果": "show_result",
    "收束": "close",
}
_CONTEXT_ACTIONS = frozenset({"show_context", "show_problem", "show_result", "close"})

# continuity_lexicon_v1: allowed role pairs and their neutral connectors.
_CONTINUITY_LEXICON: dict[tuple[str, str], tuple[str, tuple[str, ...]]] = {
    ("开场情境", "问题/需求"): ("情境 → 问题", ("先看这个场景", "先从这里开始")),
    ("开场情境", "产品出现"): ("情境 → 产品", ("这时候", "所以看产品本身")),
    ("开场情境", "功能证明"): ("情境 → 证明", ("具体看这一点", "再看实际使用")),
    ("问题/需求", "产品出现"): ("问题 → 产品", ("这时候", "所以看产品本身")),
    ("问题/需求", "功能证明"): ("问题 → 证明", ("具体看这一点", "再看实际使用")),
    ("产品出现", "功能证明"): ("产品 → 证明", ("具体看这一点", "再看实际使用")),
    ("产品出现", "使用结果"): ("产品 → 结果", ("从这个结果看", "用起来之后")),
    ("产品出现", "收束"): ("任意 → 收束", ("最后", "整体来看")),
    ("功能证明", "功能证明"): ("证明延续", ("具体看这一点", "再看实际使用")),
    ("功能证明", "使用结果"): ("证明 → 结果", ("从这个结果看", "用起来之后")),
    ("功能证明", "收束"): ("任意 → 收束", ("最后", "整体来看")),
    ("使用结果", "收束"): ("任意 → 收束", ("最后", "整体来看")),
}


class NarrativeCoherenceError(ValueError):
    """Raised when the coherence gate inputs are invalid."""


class NarrativeCoherenceBuilder:
    implementation_version = "narrative-coherence-v1"

    def build(
        self,
        *,
        content_baseline_path: Path,
        mutation_plan_path: Path,
        shot_blueprint_path: Path,
        evidence_matrix_path: Path,
    ) -> dict[str, Any]:
        paths = {
            "content_baseline.json": self._canonical_path(content_baseline_path, "content_baseline.json"),
            "mutation_plan.json": self._canonical_path(mutation_plan_path, "mutation_plan.json"),
            "shot_blueprint.json": self._canonical_path(shot_blueprint_path, "shot_blueprint.json"),
            "script_evidence_matrix.json": self._canonical_path(evidence_matrix_path, "script_evidence_matrix.json"),
        }
        baseline = read_json_object(paths["content_baseline.json"])
        mutation = read_json_object(paths["mutation_plan.json"])
        blueprint = read_json_object(paths["shot_blueprint.json"])
        evidence = read_json_object(paths["script_evidence_matrix.json"])
        for artifact, expected in (
            (baseline, "content_baseline"),
            (mutation, "mutation_plan"),
            (blueprint, "shot_blueprint"),
            (evidence, "script_evidence_matrix"),
        ):
            if artifact.get("artifact_type") != expected:
                raise NarrativeCoherenceError(f"{expected} artifact is required")

        fragments = baseline.get("fragments")
        if not isinstance(fragments, list) or not fragments:
            raise NarrativeCoherenceError("content_baseline fragments must be a non-empty array")
        forbidden = self._string_list(baseline.get("forbidden_claims", []), "forbidden_claims")
        forbidden += self._string_list(mutation.get("forbidden_claims", []), "mutation forbidden_claims")
        evidence_rows = {
            str(row.get("fragment_id")): row
            for row in evidence.get("rows", [])
            if isinstance(row, Mapping) and isinstance(row.get("fragment_id"), str)
        }

        report_fragments: list[dict[str, Any]] = []
        blocked: list[str] = []
        manual: list[str] = []
        for index, raw in enumerate(fragments):
            if not isinstance(raw, Mapping):
                raise NarrativeCoherenceError("baseline fragment must be an object")
            fragment_id = str(raw.get("fragment_id") or "")
            if not fragment_id:
                raise NarrativeCoherenceError("baseline fragment needs fragment_id")
            row = dict(raw)
            role = row.get("narrative_role")
            actions = self._string_list(row.get("required_actions", []), f"{fragment_id}.required_actions")
            manual_reasons: list[str] = []
            block_reasons: list[str] = []
            if role not in _ROLES:
                manual_reasons.append("缺少叙事元数据（narrative_contract_v1）")
            if any(action not in _ACTIONS for action in actions):
                manual_reasons.append("required_actions 包含未知动作")
            text = ""
            evidence_row = evidence_rows.get(fragment_id, {})
            if evidence_row.get("fallback") is not None and isinstance(evidence_row.get("fallback"), Mapping):
                text = str(evidence_row["fallback"].get("text", ""))
            else:
                text = str(evidence_row.get("voice_text", ""))
            for claim in forbidden:
                if claim and claim in text:
                    block_reasons.append(f"越过禁用声明边界：{claim}")
                    break
            if isinstance(role, str) and role in _ROLES and actions and not any(action in _CONTEXT_ACTIONS for action in actions) and role in {"产品出现", "功能证明"}:
                if index > 0:
                    previous = fragments[index - 1]
                    previous_role = previous.get("narrative_role") if isinstance(previous, Mapping) else None
                    previous_actions = self._string_list(previous.get("required_actions", []), "previous.required_actions") if isinstance(previous, Mapping) else []
                    if previous_role in {"产品出现", "功能证明"} and not any(action in _CONTEXT_ACTIONS for action in previous_actions):
                        block_reasons.append("相邻片段连续为纯卖点")
            reasons = [*block_reasons, *manual_reasons]
            coherence = "blocked" if block_reasons else ("manual_review" if manual_reasons else "passed")
            report_fragments.append(
                {
                    "fragment_id": fragment_id,
                    "narrative_role": role if isinstance(role, str) and role else "待确认",
                    "required_actions": actions,
                    "continuity_before": None,
                    "continuity_after": None,
                    "approved_claim_ids": self._string_list(evidence_row.get("approved_claim_ids", []), f"{fragment_id}.approved_claim_ids"),
                    "evidence_row_ref": fragment_id if fragment_id in evidence_rows else None,
                    "coherence_status": coherence,
                    "blocked_reasons": reasons,
                    "business_explanation": "；".join(reasons) if reasons else "",
                }
            )
            if coherence == "blocked":
                blocked.append(fragment_id)
            elif coherence == "manual_review":
                manual.append(fragment_id)

        for index in range(len(report_fragments) - 1):
            current, following = report_fragments[index], report_fragments[index + 1]
            if current["narrative_role"] not in _ROLES or following["narrative_role"] not in _ROLES:
                continue
            pair = (current["narrative_role"], following["narrative_role"])
            entry = _CONTINUITY_LEXICON.get(pair)
            if entry is None:
                current["coherence_status"] = "blocked"
                current["blocked_reasons"].append(f"缺少承接：{pair[0]} → {pair[1]}")
                if current["fragment_id"] not in blocked:
                    blocked.append(current["fragment_id"])
                continue
            current["continuity_after"] = entry[0]
            following["continuity_before"] = entry[0]

        opening = report_fragments[0]
        closing = report_fragments[-1]
        checks: dict[str, str] = {}
        if opening["narrative_role"] in {"开场情境", "问题/需求"}:
            checks["opening_context"] = "passed"
        elif opening["narrative_role"] not in _ROLES:
            checks["opening_context"] = "manual_review"
        else:
            checks["opening_context"] = "blocked"
        if closing["narrative_role"] == "收束" or "close" in closing["required_actions"]:
            checks["closing"] = "passed"
        elif closing["narrative_role"] not in _ROLES:
            checks["closing"] = "manual_review"
        else:
            checks["closing"] = "blocked"
        transition_blocked = any(
            row["coherence_status"] == "blocked" for row in report_fragments
        )
        transition_manual = any(
            row["coherence_status"] == "manual_review" for row in report_fragments
        )
        checks["transition_coverage"] = "manual_review" if transition_manual and not transition_blocked else ("blocked" if transition_blocked else "passed")
        pure_claims = [
            row["fragment_id"] for row in report_fragments
            if any("连续为纯卖点" in reason for reason in row["blocked_reasons"])
        ]
        checks["claim_density"] = "blocked" if pure_claims else "passed"
        for fragment_id in pure_claims:
            if fragment_id not in blocked:
                blocked.append(fragment_id)

        status = "blocked" if (blocked or any(check == "blocked" for check in checks.values())) else (
            "manual_review" if (manual or any(check == "manual_review" for check in checks.values())) else "passed"
        )
        return {
            "artifact_type": "narrative_coherence_report",
            "schema_id": "urn:capcut:remix-reference-video:artifact:narrative-coherence-report",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "implementation_version": self.implementation_version,
            "lifecycle_status": "ready",
            "input_hashes": {name: self._sha256(path) for name, path in paths.items()},
            "status": status,
            "narrative_contract_version": NARRATIVE_CONTRACT_VERSION,
            "continuity_lexicon_version": CONTINUITY_LEXICON_VERSION,
            "fragments": report_fragments,
            "checks": checks,
            "blocked_fragment_ids": list(dict.fromkeys([*blocked, *manual])),
            "allowed_resolutions": ["rewrite_copy", "use_approved_fallback", "return_gate2"],
        }

    @staticmethod
    def _canonical_path(path: Path, expected_name: str) -> Path:
        requested = Path(path)
        if requested.name != expected_name:
            raise NarrativeCoherenceError(f"input path must be {expected_name}")
        if requested.is_symlink():
            raise NarrativeCoherenceError(f"{expected_name} must not be a symlink")
        return requested.resolve(strict=True)

    @staticmethod
    def _string_list(value: object, field: str) -> list[str]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise NarrativeCoherenceError(f"{field} must contain strings")
        return list(value)

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
