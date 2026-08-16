"""Pre-TTS duration budget checks against Gate 3 broad ranges."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping


class VoicePreflightError(ValueError):
    pass


class VoicePreflight:
    implementation_version = "voice-preflight-v1"
    default_articulation_chars_per_second = 4.6
    punctuation_pause_seconds = {
        "，": 0.75,
        ",": 0.65,
        "、": 0.35,
        "；": 0.55,
        ";": 0.45,
        "：": 0.4,
        ":": 0.35,
        "。": 0.35,
        ".": 0.3,
        "！": 0.4,
        "!": 0.35,
        "？": 0.4,
        "?": 0.35,
    }

    def build(
        self,
        *,
        production_script: Mapping[str, object],
        fragment_plan: Mapping[str, object],
        speed: float,
        articulation_chars_per_second: float | None = None,
    ) -> dict[str, object]:
        if production_script.get("artifact_type") != "production_script_candidate":
            raise VoicePreflightError("production script candidate is required")
        if fragment_plan.get("artifact_type") != "fragment_plan":
            raise VoicePreflightError("fragment plan is required")
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or speed <= 0:
            raise VoicePreflightError("voice speed must be positive")
        chars_per_second = (
            self.default_articulation_chars_per_second
            if articulation_chars_per_second is None
            else articulation_chars_per_second
        )
        if (
            isinstance(chars_per_second, bool)
            or not isinstance(chars_per_second, (int, float))
            or chars_per_second <= 0
        ):
            raise VoicePreflightError("articulation chars per second must be positive")

        lines = self._by_fragment(production_script.get("lines"), "script")
        plans = self._by_fragment(fragment_plan.get("fragments"), "fragment plan")
        rows: list[dict[str, object]] = []
        for fragment_id, line in lines.items():
            plan = plans.get(fragment_id)
            if plan is None:
                raise VoicePreflightError(f"{fragment_id} is missing fragment plan")
            text = line.get("text")
            if not isinstance(text, str) or not text.strip():
                raise VoicePreflightError(f"{fragment_id} script text is invalid")
            content_chars = sum(
                1
                for character in text
                if not character.isspace()
                and not unicodedata.category(character).startswith("P")
            )
            pause_seconds = sum(
                self.punctuation_pause_seconds.get(character, 0.0)
                for character in text
            )
            estimate = (content_chars / float(chars_per_second) + pause_seconds) / float(speed)
            source_path = str(plan.get("source_path", ""))
            media_type = plan.get("media_type")
            if media_type not in {"video", "image"}:
                media_type = (
                    "image"
                    if source_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                    else "video"
                )
            image = media_type == "image"
            budget: float | None
            margin: float | None
            status = "passed"
            if image:
                budget = None
                margin = None
            else:
                broad = plan.get("approved_broad_range")
                if not isinstance(broad, Mapping):
                    raise VoicePreflightError(f"{fragment_id} has no Gate 3 broad range")
                start = broad.get("start_seconds")
                end = broad.get("end_seconds")
                if (
                    isinstance(start, bool)
                    or isinstance(end, bool)
                    or not isinstance(start, (int, float))
                    or not isinstance(end, (int, float))
                    or end <= start
                ):
                    raise VoicePreflightError(f"{fragment_id} Gate 3 broad range is invalid")
                range_budget = float(end) - float(start)
                declared_budget = plan.get("visual_duration_budget_seconds")
                if declared_budget is None:
                    budget = range_budget
                elif (
                    isinstance(declared_budget, bool)
                    or not isinstance(declared_budget, (int, float))
                    or declared_budget <= 0
                    or not math.isclose(
                        float(declared_budget), range_budget, abs_tol=1e-6
                    )
                ):
                    raise VoicePreflightError(
                        f"{fragment_id} visual duration budget does not match Gate 3 broad range"
                    )
                else:
                    budget = float(declared_budget)
                margin = budget - estimate
                if margin < 0:
                    status = "blocked"
            rows.append(
                {
                    "fragment_id": fragment_id,
                    "media_type": media_type,
                    "text_character_count": content_chars,
                    "estimated_punctuation_pause_seconds": round(pause_seconds, 3),
                    "visual_duration_budget_seconds": self._round_or_none(budget),
                    "voice_duration_estimate_seconds": round(estimate, 3),
                    "voice_duration_margin_seconds": self._round_or_none(margin),
                    "preflight_status": status,
                }
            )
        blocked = [row["fragment_id"] for row in rows if row["preflight_status"] == "blocked"]
        return {
            "artifact_type": "voice_preflight",
            "schema_id": "urn:capcut:remix-reference-video:artifact:voice-preflight",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "preflight_status": "blocked" if blocked else "passed",
            "speed": float(speed),
            "estimator": {
                "implementation_version": self.implementation_version,
                "articulation_chars_per_second": float(chars_per_second),
                "punctuation_pause_model": "speaker_history_v1",
            },
            "blocked_fragment_ids": blocked,
            "fragments": rows,
            "allowed_resolutions": [
                "shorten_script",
                "use_gate2_approved_fallback",
                "expand_gate3_broad_range",
                "return_to_gate2_for_structure_change",
            ] if blocked else [],
        }

    @staticmethod
    def _by_fragment(value: object, field: str) -> dict[str, Mapping[str, object]]:
        if not isinstance(value, list) or not value:
            raise VoicePreflightError(f"{field} rows must be a non-empty array")
        result: dict[str, Mapping[str, object]] = {}
        for row in value:
            if not isinstance(row, Mapping) or not isinstance(row.get("fragment_id"), str):
                raise VoicePreflightError(f"{field} row is invalid")
            fragment_id = str(row["fragment_id"])
            if fragment_id in result:
                raise VoicePreflightError(f"duplicate {field} fragment: {fragment_id}")
            result[fragment_id] = row
        return result

    @staticmethod
    def _round_or_none(value: float | None) -> float | None:
        if value is None:
            return None
        rounded = round(value, 3)
        return 0.0 if math.isclose(rounded, 0.0, abs_tol=1e-9) else rounded


__all__ = ["VoicePreflight", "VoicePreflightError"]
