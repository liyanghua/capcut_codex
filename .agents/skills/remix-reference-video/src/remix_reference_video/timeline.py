"""Measured voice-driven reconstruction timeline and sidecar captions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class TimelineError(ValueError):
    pass


class TimelineBuilder:
    def build(
        self,
        *,
        approved_script: Mapping[str, object],
        fragment_plan: Mapping[str, object],
        voice_manifest: Mapping[str, object],
    ) -> dict[str, object]:
        if approved_script.get("artifact_type") != "approved_production_script":
            raise TimelineError("approved production script is required")
        if fragment_plan.get("artifact_type") != "fragment_plan":
            raise TimelineError("fragment plan is required")
        if voice_manifest.get("artifact_type") != "voice_manifest":
            raise TimelineError("voice manifest is required")
        scripts = self._by_id(approved_script.get("lines"), "script")
        plans = self._by_id(fragment_plan.get("fragments"), "fragment plan")
        voices = self._by_id(voice_manifest.get("segments"), "voice manifest")
        timeline_rows: list[dict[str, Any]] = []
        cues: list[str] = []
        cursor = 0.0
        for index, (fragment_id, line) in enumerate(scripts.items(), 1):
            if fragment_id not in plans or fragment_id not in voices:
                raise TimelineError(f"{fragment_id} is missing plan or measured voice")
            duration = voices[fragment_id].get("measured_duration_seconds")
            if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
                raise TimelineError(f"{fragment_id} measured voice duration is invalid")
            broad = plans[fragment_id].get("approved_broad_range")
            if not isinstance(broad, Mapping):
                raise TimelineError(f"{fragment_id} has no Gate 3 broad range")
            source_start, broad_end = broad.get("start_seconds"), broad.get("end_seconds")
            source_path = str(plans[fragment_id].get("source_path", ""))
            media_type = plans[fragment_id].get("media_type")
            if media_type not in {"video", "image"}:
                media_type = (
                    "image"
                    if source_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                    else "video"
                )
            image = media_type == "image"
            if image:
                source_end = None
            else:
                if not isinstance(source_start, (int, float)) or not isinstance(broad_end, (int, float)):
                    raise TimelineError(f"{fragment_id} Gate 3 broad range is invalid")
                source_end = float(source_start) + float(duration)
                if source_end > float(broad_end) + 1e-9:
                    raise TimelineError(f"{fragment_id} exact range exceeds Gate 3 broad range")
            end = cursor + float(duration)
            text = line.get("text")
            if not isinstance(text, str) or not text:
                raise TimelineError(f"{fragment_id} script text is invalid")
            timeline_row = {
                    "fragment_id": fragment_id,
                    "timeline_start_seconds": round(cursor, 6),
                    "timeline_end_seconds": round(end, 6),
                    "source_start_seconds": None if image else float(source_start),
                    "source_end_seconds": None if image else round(float(source_end), 6),
                    "playback_speed": 1.0,
                    "text": text,
                }
            if image:
                timeline_row["display_duration_seconds"] = float(duration)
            timeline_rows.append(timeline_row)
            cues.append(
                f"{index}\n{_srt_time(cursor)} --> {_srt_time(end)}\n{text}\n"
            )
            cursor = end
        return {
            "timeline": {
                "artifact_type": "reconstruction_timeline",
                "schema_id": "urn:capcut:remix-reference-video:artifact:reconstruction-timeline",
                "schema_version": "1.0.0",
                "contract_version": "2.0.0-alpha.1",
                "skill_version": "2.0.0-alpha.1",
                "duration_seconds": round(cursor, 6),
                "fragments": timeline_rows,
            },
            "captions_srt": "\n".join(cues),
        }

    @staticmethod
    def _by_id(value: object, field: str) -> dict[str, Mapping[str, object]]:
        if not isinstance(value, list):
            raise TimelineError(f"{field} rows must be an array")
        result: dict[str, Mapping[str, object]] = {}
        for row in value:
            if not isinstance(row, Mapping) or not isinstance(row.get("fragment_id"), str):
                raise TimelineError(f"{field} row is invalid")
            fragment_id = str(row["fragment_id"])
            if fragment_id in result:
                raise TimelineError(f"duplicate {field} fragment: {fragment_id}")
            result[fragment_id] = row
        return result


def _srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{millis:03d}"
