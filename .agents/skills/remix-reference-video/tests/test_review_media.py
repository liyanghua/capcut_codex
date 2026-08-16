from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.review_media import build_gate3_review_media


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
class ReviewMediaTests(unittest.TestCase):
    def test_gate3_review_media_binds_sheet_and_video_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = root / "task"
            assets = root / "assets"
            (task / "gate_review_packages").mkdir(parents=True)
            assets.mkdir()
            video = assets / "clip.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=green:s=360x640:r=30:d=0.5",
                "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
            ], check=True)
            package = task / "gate_review_packages" / "gate3_material_selection.json"
            package.write_text(json.dumps({
                "gate_id": "gate3_material_selection", "input_hashes": {},
                "selections": [{"fragment_id": "fragment01", "source_path": "clip.mp4",
                    "approved_broad_range": {"start_seconds": 0.0, "end_seconds": 0.5}}],
            }), encoding="utf-8")
            result = build_gate3_review_media(
                task_root=task, asset_root=assets, package_path=package
            )
            self.assertTrue((task / "gate3_review_contact_sheet.jpg").is_file())
            self.assertTrue((task / "gate3_review_proxies/fragment01.mp4").is_file())
            self.assertIn("gate3_review_contact_sheet.jpg", result["input_hashes"])


if __name__ == "__main__":
    unittest.main()
