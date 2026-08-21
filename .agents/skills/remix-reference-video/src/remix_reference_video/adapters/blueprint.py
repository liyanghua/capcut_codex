"""Compile Blueprint drafts within Brief-approved claim boundaries."""

from __future__ import annotations

import math
import hashlib
import json
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
            row["visual_intent"] = self._visual_intent(row)
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

    def build_creative_objective(
        self,
        *,
        brief: Mapping[str, object],
        selected_decomposition_id: str,
        gate1_selection_hash: str,
    ) -> dict[str, Any]:
        """Build a non-authoritative Gate 2 target from frozen facts only."""
        if not isinstance(selected_decomposition_id, str) or not selected_decomposition_id:
            raise BlueprintValidationError("selected decomposition is required")
        if not self._sha256(gate1_selection_hash):
            raise BlueprintValidationError("Gate 1 selection hash is invalid")
        config = brief.get("creative_objective", {})
        if config is None:
            config = {}
        if not isinstance(config, Mapping):
            raise BlueprintValidationError("creative_objective must be an object")
        if any(field in config for field in ("product", "platform", "audience", "target")):
            raise BlueprintValidationError("creative objective cannot override frozen identity fields")
        product = brief.get("product")
        target = brief.get("target")
        if not isinstance(product, Mapping) or not isinstance(target, Mapping):
            raise BlueprintValidationError("frozen product and target identity are required")
        product_name, audience, platform = product.get("name"), product.get("audience"), target.get("platform")
        if not all(isinstance(value, str) and value for value in (product_name, audience, platform)):
            raise BlueprintValidationError("frozen product, audience and platform are required")
        approved = self._claims(brief.get("approved_claims"))
        forbidden = self._strings(brief.get("forbidden_claims", ()), "forbidden_claims")
        envelope = self._duration_envelope(brief.get("duration_envelope"))
        appearance_target = config.get("product_appearance_target_seconds")
        if appearance_target is not None and (
            isinstance(appearance_target, bool) or not isinstance(appearance_target, (int, float)) or appearance_target < 0
        ):
            raise BlueprintValidationError("product appearance target is invalid")
        exception = config.get("product_appearance_exception")
        if exception is not None and (not isinstance(exception, str) or not exception):
            raise BlueprintValidationError("product appearance exception is invalid")
        objectives = self._creative_objectives(approved)
        brief_hash = self._digest(brief)
        objective_seed = f"{brief_hash}:{selected_decomposition_id}:{gate1_selection_hash}"
        return {
            **_ENVELOPE,
            "artifact_type": "creative_objective",
            "schema_id": "urn:capcut:remix-reference-video:artifact:creative-objective",
            "implementation_version": "creative-objective-builder-v1",
            "lifecycle_status": "ready",
            "input_hashes": {
                "project_brief.json": brief_hash,
                "gate1_decomposition_selection": gate1_selection_hash,
            },
            "objective_id": hashlib.sha256(objective_seed.encode("utf-8")).hexdigest()[:16],
            "objective_version": "creative_objective_v1",
            "objective_contract_version": "creative_objective_v1",
            "platform": platform,
            "audience": audience,
            "product": product_name,
            "duration_envelope": {
                "min_seconds": float(envelope["minimum_seconds"]),
                "max_seconds": float(envelope["maximum_seconds"]),
            },
            "core_message": str(config.get("core_message", next(iter(approved.values()))["text"])),
            "desired_action": str(config.get("desired_action", "not_specified")),
            "opening_hook_hypothesis": str(config.get("opening_hook_hypothesis", "not_specified")),
            "approved_claims": [row["text"] for row in approved.values()],
            "forbidden_claims": forbidden,
            "product_appearance_target_seconds": None if appearance_target is None else float(appearance_target),
            "product_appearance_exception": exception,
            "cta": str(config.get("cta", "not_required")),
            "objectives": objectives,
        }

    @staticmethod
    def _visual_intent(fragment: Mapping[str, object]) -> dict[str, object]:
        raw_ids = fragment.get("reference_shot_ids")
        if not isinstance(raw_ids, list):
            raw_ids = [fragment["reference_shot_id"]] if isinstance(fragment.get("reference_shot_id"), str) else []
        return {
            "reference_shot_ids": [item for item in raw_ids if isinstance(item, str) and item],
            "required_actions": list(fragment.get("required_actions", [])),
            "claim_ids": list(fragment.get("claim_ids", [])),
            "narrative_role": fragment.get("narrative_role"),
        }

    @staticmethod
    def _creative_objectives(approved: Mapping[str, Mapping[str, object]]) -> list[dict[str, object]]:
        base = [
            {"objective_id": "opening_hook", "required": True, "description": "前三秒建立观看动机"},
            {"objective_id": "product_appearance", "required": True, "description": "商品清晰出现"},
            *[
                {"objective_id": f"claim:{claim_id}", "required": True, "description": str(row["text"])}
                for claim_id, row in approved.items()
            ],
            {"objective_id": "close", "required": True, "description": "自然收束"},
        ]
        weight = 1.0 / len(base)
        for row in base:
            row["weight"] = weight
        base[-1]["weight"] = 1.0 - sum(float(row["weight"]) for row in base[:-1])
        return base

    @staticmethod
    def _digest(value: object) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _sha256(value: object) -> bool:
        return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)

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
