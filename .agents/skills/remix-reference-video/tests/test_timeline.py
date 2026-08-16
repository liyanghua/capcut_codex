from __future__ import annotations

import unittest

from remix_reference_video.timeline import TimelineBuilder, TimelineError


class TimelineBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.script = {
            "artifact_type": "approved_production_script",
            "lines": [
                {"fragment_id": "fragment01", "text": "第一句。"},
                {"fragment_id": "fragment02", "text": "第二句。"},
            ],
        }
        self.plan = {
            "artifact_type": "fragment_plan",
            "lifecycle_status": "approved",
            "fragments": [
                {
                    "fragment_id": "fragment01",
                    "approved_broad_range": {"start_seconds": 0.5, "end_seconds": 3.5},
                },
                {
                    "fragment_id": "fragment02",
                    "approved_broad_range": {"start_seconds": 1.0, "end_seconds": 4.0},
                },
            ],
        }
        self.voice = {
            "artifact_type": "voice_manifest",
            "segments": [
                {"fragment_id": "fragment01", "measured_duration_seconds": 2.25},
                {"fragment_id": "fragment02", "measured_duration_seconds": 1.5},
            ],
        }

    def test_uses_measured_duration_with_nonoverlapping_subtitles_and_one_x_video(self) -> None:
        result = TimelineBuilder().build(
            approved_script=self.script,
            fragment_plan=self.plan,
            voice_manifest=self.voice,
        )
        rows = result["timeline"]["fragments"]
        self.assertEqual(rows[0]["timeline_start_seconds"], 0.0)
        self.assertEqual(rows[0]["timeline_end_seconds"], 2.25)
        self.assertEqual(rows[1]["timeline_start_seconds"], 2.25)
        self.assertEqual(rows[1]["timeline_end_seconds"], 3.75)
        self.assertEqual(rows[0]["source_start_seconds"], 0.5)
        self.assertEqual(rows[0]["source_end_seconds"], 2.75)
        self.assertEqual(rows[0]["playback_speed"], 1.0)
        self.assertIn("00:00:00,000 --> 00:00:02,250", result["captions_srt"])
        self.assertIn("00:00:02,250 --> 00:00:03,750", result["captions_srt"])

    def test_exact_range_must_remain_inside_gate3_broad_range(self) -> None:
        self.voice["segments"][0]["measured_duration_seconds"] = 3.25
        with self.assertRaisesRegex(TimelineError, "Gate 3 broad range"):
            TimelineBuilder().build(
                approved_script=self.script,
                fragment_plan=self.plan,
                voice_manifest=self.voice,
            )

    def test_image_fragment_uses_voice_duration_without_video_source_range(self) -> None:
        result = TimelineBuilder().build(
            approved_script={
                "artifact_type": "approved_production_script",
                "lines": [{"fragment_id": "fragment01", "text": "产品细节"}],
            },
            fragment_plan={
                "artifact_type": "fragment_plan",
                "fragments": [{
                    "fragment_id": "fragment01",
                    "source_path": "asset-without-extension",
                    "media_type": "image",
                    "approved_broad_range": {
                        "start_seconds": None,
                        "end_seconds": None,
                    },
                }],
            },
            voice_manifest={
                "artifact_type": "voice_manifest",
                "segments": [{
                    "fragment_id": "fragment01",
                    "measured_duration_seconds": 1.25,
                }],
            },
        )
        row = result["timeline"]["fragments"][0]
        self.assertIsNone(row["source_start_seconds"])
        self.assertIsNone(row["source_end_seconds"])
        self.assertEqual(row["display_duration_seconds"], 1.25)

    def test_image_fragment_normalizes_legacy_numeric_broad_range(self) -> None:
        result = TimelineBuilder().build(
            approved_script={
                "artifact_type": "approved_production_script",
                "lines": [{"fragment_id": "fragment01", "text": "产品细节"}],
            },
            fragment_plan={
                "artifact_type": "fragment_plan",
                "fragments": [{
                    "fragment_id": "fragment01",
                    "source_path": "detail.jpg",
                    "approved_broad_range": {
                        "start_seconds": 0.0,
                        "end_seconds": 60.0,
                    },
                }],
            },
            voice_manifest={
                "artifact_type": "voice_manifest",
                "segments": [{
                    "fragment_id": "fragment01",
                    "measured_duration_seconds": 1.25,
                }],
            },
        )
        row = result["timeline"]["fragments"][0]
        self.assertIsNone(row["source_start_seconds"])
        self.assertIsNone(row["source_end_seconds"])
        self.assertEqual(row["display_duration_seconds"], 1.25)


if __name__ == "__main__":
    unittest.main()
