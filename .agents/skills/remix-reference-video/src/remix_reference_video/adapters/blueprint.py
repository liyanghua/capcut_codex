"""Compile Blueprint drafts within Brief-approved claim boundaries."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from ..narrative_coherence import NARRATIVE_CONTRACT_VERSION, _ACTIONS, _ROLES


class BlueprintValidationError(ValueError):
    """Raised when a Blueprint draft exceeds its approved inputs."""


_ENVELOPE = {
    "schema_version": "1.0.0",
    "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
}


class BlueprintAdapter:
    implementation_version = "blueprint-adapter-v1"

    def compile(
        self,
        *,
        brief: Mapping[str, object],
        recipe: Mapping[str, object],
        coverage_precheck: Mapping[str, object],
        target_fragments: Sequence[Mapping[str, object]],
    ) -> dict[str, dict[str, Any]]:
        if recipe.get("artifact_type") != "recipe":
            raise BlueprintValidationError("recipe artifact is required")
        if (
            coverage_precheck.get("artifact_type") != "coverage_precheck"
            or coverage_precheck.get("scope") != "precheck"
        ):
            raise BlueprintValidationError("coverage_precheck advisory artifact is required")
        approved = self._claims(brief.get("approved_claims"))
        forbidden = self._strings(brief.get("forbidden_claims", ()), "forbidden_claims")
        fragments = [dict(row) for row in target_fragments]
        used_claim_ids: set[str] = set()
        narration = ""
        for row in fragments:
            fragment_id = row.get("fragment_id")
            if not isinstance(fragment_id, str) or not fragment_id:
                raise BlueprintValidationError("every target fragment needs fragment_id")
            claim_ids = self._strings(row.get("claim_ids", ()), f"{fragment_id}.claim_ids")
            unknown = [claim_id for claim_id in claim_ids if claim_id not in approved]
            if unknown:
                raise BlueprintValidationError(
                    f"{fragment_id} uses unapproved claim: {', '.join(unknown)}"
                )
            text = row.get("narration", "")
            if not isinstance(text, str):
                raise BlueprintValidationError(f"{fragment_id}.narration must be text")
            role = row.get("narrative_role")
            if not isinstance(role, str) or role not in _ROLES:
                raise BlueprintValidationError(
                    f"{fragment_id}.narrative_role must be one of {_ROLES!r}"
                )
            actions = self._strings(row.get("required_actions", ()), f"{fragment_id}.required_actions")
            if not actions:
                raise BlueprintValidationError(f"{fragment_id}.required_actions must not be empty")
            if any(action not in _ACTIONS for action in actions):
                raise BlueprintValidationError(
                    f"{fragment_id}.required_actions must be within {_ACTIONS!r}"
                )
            blocked = [claim for claim in forbidden if claim and claim in text]
            if blocked:
                raise BlueprintValidationError(
                    f"{fragment_id} uses forbidden claim: {', '.join(blocked)}"
                )
            used_claim_ids.update(claim_ids)
            narration += text
        envelope = self._duration_envelope(brief.get("duration_envelope"))
        timing = self._timing_lint(
            narration,
            envelope,
            brief.get("maximum_narration_chars_per_second"),
        )
        blueprint = {
            **_ENVELOPE,
            "artifact_type": "shot_blueprint",
            "schema_id": "urn:capcut:remix-reference-video:artifact:shot-blueprint",
            "implementation_version": self.implementation_version,
            "coverage_role": "advisory_only",
            "fragments": fragments,
        }
        baseline = {
            **_ENVELOPE,
            "artifact_type": "content_baseline",
            "schema_id": "urn:capcut:remix-reference-video:artifact:content-baseline",
            "claims": [approved[item] for item in sorted(used_claim_ids)],
            "forbidden_claims": forbidden,
            "fragments": fragments,
            "duration_envelope": envelope,
            "timing_lint": timing,
            "narrative_contract_version": NARRATIVE_CONTRACT_VERSION,
            "lifecycle_status": "draft",
        }
        return {"shot_blueprint": blueprint, "content_baseline": baseline}

    @staticmethod
    def _claims(value: object) -> dict[str, dict[str, object]]:
        if not isinstance(value, list):
            raise BlueprintValidationError("approved_claims must be an array")
        claims: dict[str, dict[str, object]] = {}
        for row in value:
            if not isinstance(row, Mapping):
                raise BlueprintValidationError("approved claim must be an object")
            claim_id, text = row.get("claim_id"), row.get("text")
            if not isinstance(claim_id, str) or not claim_id or not isinstance(text, str) or not text:
                raise BlueprintValidationError("approved claim needs claim_id and text")
            if claim_id in claims:
                raise BlueprintValidationError(f"duplicate approved claim: {claim_id}")
            claims[claim_id] = dict(row)
        return claims

    @staticmethod
    def _strings(value: object, field: str) -> list[str]:
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise BlueprintValidationError(f"{field} must contain nonempty strings")
        return list(value)

    @staticmethod
    def _duration_envelope(value: object) -> dict[str, object]:
        if not isinstance(value, Mapping):
            raise BlueprintValidationError("duration_envelope must be an object")
        minimum, maximum = value.get("minimum_seconds"), value.get("maximum_seconds")
        if (
            isinstance(minimum, bool)
            or isinstance(maximum, bool)
            or not isinstance(minimum, (int, float))
            or not isinstance(maximum, (int, float))
            or minimum <= 0
            or maximum < minimum
        ):
            raise BlueprintValidationError("duration_envelope range is invalid")
        if value.get("strength") != "soft":
            raise BlueprintValidationError("duration_envelope must be soft")
        return dict(value)

    @staticmethod
    def _timing_lint(
        narration: str,
        envelope: Mapping[str, object],
        raw_rate: object,
    ) -> dict[str, object]:
        if isinstance(raw_rate, bool) or not isinstance(raw_rate, (int, float)) or raw_rate <= 0:
            raise BlueprintValidationError("maximum_narration_chars_per_second is invalid")
        character_count = sum(not char.isspace() for char in narration)
        estimated = character_count / float(raw_rate)
        minimum = float(envelope["minimum_seconds"])
        maximum = float(envelope["maximum_seconds"])
        recommended = max(minimum, estimated)
        status = "duration_expansion_required" if estimated > maximum else "within_soft_envelope"
        return {
            "status": status,
            "character_count": character_count,
            "maximum_chars_per_second": float(raw_rate),
            "recommended_duration_seconds": math.ceil(recommended * 1000) / 1000,
        }
