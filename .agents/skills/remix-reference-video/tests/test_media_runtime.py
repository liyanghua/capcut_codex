from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.media_runtime import FFmpegMediaProbe, FFmpegRenderer


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required"
)
class MediaRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()

    def test_probe_reports_gate5_media_contract(self) -> None:
        media = self.root / "sample.mp4"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=red:s=1080x1920:r=60:d=0.2",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=0.2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-shortest", str(media),
            ],
            check=True,
        )
        result = FFmpegMediaProbe()(media)
        self.assertEqual(
            (result["width"], result["height"], result["fps"]),
            (1080, 1920, 60),
        )
        self.assertEqual(result["video_codec"], "h264")
        self.assertEqual(result["audio_codec"], "aac")
        self.assertEqual(result["audio_sample_rate"], 44100)

    def test_renderer_assembles_approved_material_and_voice(self) -> None:
        task = self.root / "task"
        material = task / "material" / "fragment01"
        voice = task / "voice"
        material.mkdir(parents=True)
        voice.mkdir()
        source = material / "clip.mp4"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=720x1280:r=30:d=0.5",
                "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
            ],
            check=True,
        )
        final_voice = voice / "final_voice.mp3"
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=0.5",
                "-c:a", "libmp3lame", str(final_voice),
            ],
            check=True,
        )
        (voice / "voice_manifest.json").write_text(
            json.dumps({
                "artifact_type": "voice_manifest",
                "final_voice": {"path": "final_voice.mp3"},
            }),
            encoding="utf-8",
        )
        manifest = task / "material_manifest.json"
        manifest.write_text(
            json.dumps({
                "artifact_type": "material_manifest",
                "fragments": [{
                    "fragment_id": "fragment01",
                    "material_path": "material/fragment01/clip.mp4",
                }],
            }),
            encoding="utf-8",
        )
        output = task / "remix.mp4"
        FFmpegRenderer()(
            output_path=output,
            timeline={
                "artifact_type": "reconstruction_timeline",
                "duration_seconds": 0.5,
                "fragments": [{
                    "fragment_id": "fragment01",
                    "timeline_start_seconds": 0.0,
                    "timeline_end_seconds": 0.5,
                    "source_start_seconds": 0.0,
                    "source_end_seconds": 0.5,
                    "playback_speed": 1.0,
                }],
            },
            material_manifest=manifest,
            captions_path=task / "captions.srt",
            profile={"width": 1080, "height": 1920, "fps": 60},
        )
        result = FFmpegMediaProbe()(output)
        self.assertEqual(
            (result["width"], result["height"], result["fps"]),
            (1080, 1920, 60),
        )
        self.assertEqual(result["audio_stream_count"], 1)
        self.assertLessEqual(
            abs(result["duration_seconds"] - 0.5), 1 / 60 + 0.01
        )


if __name__ == "__main__":
    unittest.main()
