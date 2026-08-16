from __future__ import annotations

import unittest

from remix_reference_video.voice_preflight import VoicePreflight


class VoicePreflightTests(unittest.TestCase):
    def test_video_budget_blocks_negative_margin_and_images_have_no_budget(self) -> None:
        report = VoicePreflight().build(
            production_script={
                "artifact_type": "production_script_candidate",
                "lines": [
                    {"fragment_id": "fragment05", "text": "油污倒上去。"},
                    {"fragment_id": "fragment07", "text": "柔韧，铺开更服帖。"},
                    {"fragment_id": "fragment09", "text": "一年发黄险。"},
                ],
            },
            fragment_plan={
                "artifact_type": "fragment_plan",
                "fragments": [
                    {
                        "fragment_id": "fragment05",
                        "source_path": "pour.mp4",
                        "approved_broad_range": {
                            "start_seconds": 7.4,
                            "end_seconds": 8.8,
                        },
                    },
                    {
                        "fragment_id": "fragment07",
                        "source_path": "install.mp4",
                        "approved_broad_range": {
                            "start_seconds": 0.0,
                            "end_seconds": 2.448,
                        },
                    },
                    {
                        "fragment_id": "fragment09",
                        "source_path": "asset-without-extension",
                        "media_type": "image",
                        "approved_broad_range": {
                            "start_seconds": None,
                            "end_seconds": None,
                        },
                    },
                ],
            },
            speed=1.0,
        )

        rows = {row["fragment_id"]: row for row in report["fragments"]}
        self.assertEqual(report["preflight_status"], "blocked")
        self.assertEqual(rows["fragment05"]["visual_duration_budget_seconds"], 1.4)
        self.assertLess(rows["fragment05"]["voice_duration_margin_seconds"], 0)
        self.assertEqual(rows["fragment05"]["preflight_status"], "blocked")
        self.assertEqual(rows["fragment07"]["visual_duration_budget_seconds"], 2.448)
        self.assertLess(rows["fragment07"]["voice_duration_margin_seconds"], 0)
        self.assertIsNone(rows["fragment09"]["visual_duration_budget_seconds"])
        self.assertIsNone(rows["fragment09"]["voice_duration_margin_seconds"])
        self.assertEqual(rows["fragment09"]["preflight_status"], "passed")

    def test_sufficient_video_budget_passes(self) -> None:
        report = VoicePreflight().build(
            production_script={
                "artifact_type": "production_script_candidate",
                "lines": [{"fragment_id": "fragment01", "text": "擦净。"}],
            },
            fragment_plan={
                "artifact_type": "fragment_plan",
                "fragments": [{
                    "fragment_id": "fragment01",
                    "source_path": "wipe.mp4",
                    "approved_broad_range": {
                        "start_seconds": 0.0,
                        "end_seconds": 2.0,
                    },
                }],
            },
            speed=1.0,
        )

        row = report["fragments"][0]
        self.assertEqual(report["preflight_status"], "passed")
        self.assertEqual(row["preflight_status"], "passed")
        self.assertGreaterEqual(row["voice_duration_margin_seconds"], 0)

    def test_rejects_gate3_budget_that_disagrees_with_approved_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "duration budget"):
            VoicePreflight().build(
                production_script={
                    "artifact_type": "production_script_candidate",
                    "lines": [{"fragment_id": "fragment01", "text": "擦净。"}],
                },
                fragment_plan={
                    "artifact_type": "fragment_plan",
                    "fragments": [{
                        "fragment_id": "fragment01",
                        "media_type": "video",
                        "source_path": "wipe.mp4",
                        "visual_duration_budget_seconds": 1.0,
                        "approved_broad_range": {
                            "start_seconds": 0.0,
                            "end_seconds": 2.0,
                        },
                    }],
                },
                speed=1.0,
            )


if __name__ == "__main__":
    unittest.main()
