from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from remix_reference_video.adapters.reconstruction import ReconstructionAdapter


class ProxyValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.task = self.root / "task"
        self.assets = self.root / "assets"
        self.task.mkdir()
        self.assets.mkdir()
        self.adapter = ReconstructionAdapter(self.task, self.assets)
        self.timeline = {
            "artifact_type": "reconstruction_timeline",
            "fragments": [
                {"fragment_id": "fragment01", "timeline_start_seconds": 0.0, "timeline_end_seconds": 2.0},
                {"fragment_id": "fragment02", "timeline_start_seconds": 2.0, "timeline_end_seconds": 4.0},
            ],
        }

    def test_proxy_profile_and_boundary_frames(self) -> None:
        default = self.adapter.proxy_profile({})
        override = self.adapter.proxy_profile({"proxy_profile": "review_high"})
        self.assertEqual(default, {"width": 540, "height": 960, "fps": 30})
        self.assertEqual(override, {"width": 720, "height": 1280, "fps": 30})
        report = self.adapter.validate_proxy_boundaries(
            timeline=self.timeline,
            observed_frame_times=[1.967, 2.0, 2.033],
            fps=30,
        )
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["boundary_frames"][0]["boundary_seconds"], 2.0)

    def test_proxy_render_requires_gate4_post_approval(self) -> None:
        calls: list[dict[str, object]] = []
        with self.assertRaisesRegex(ValueError, "Gate 4 post"):
            self.adapter.render_proxy(
                timeline=self.timeline,
                gate_status={"gate4_post_generation": "awaiting_user"},
                task_config={},
                renderer=lambda **kwargs: calls.append(kwargs),
            )
        self.assertEqual(calls, [])
        result = self.adapter.render_proxy(
            timeline=self.timeline,
            gate_status={"gate4_post_generation": "approved", "gate4": "approved"},
            task_config={},
            renderer=lambda **kwargs: calls.append(kwargs) or {"path": "proxy.mp4"},
        )
        self.assertEqual(result["path"], "proxy.mp4")
        self.assertEqual(calls[0]["profile"]["width"], 540)


if __name__ == "__main__":
    unittest.main()
