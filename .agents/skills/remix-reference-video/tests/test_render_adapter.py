from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from remix_reference_video.adapters.render import RenderAdapter, RenderError
from remix_reference_video.storage import TaskStorage, atomic_write_json


class RenderAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.store = TaskStorage(self.root)
        self.store.initialize_state(
            {
                "execution_mode": "track-b-production",
                "run_id": "run-1",
                "state_revision": 0,
                "active_stage": "render-final",
                "active_command": None,
                "stage_status": {},
                "stages": {
                    "reference_split": {"status": "approved"},
                    "content_blueprint": {"status": "approved"},
                },
                "gate_status": {
                    "gate1": "approved",
                    "gate2": "approved",
                    "gate3_material_selection": "approved",
                    "gate3_evidence_closure": "approved",
                    "gate3": "approved",
                    "gate4_pre_generation": "approved",
                    "gate4_post_generation": "approved",
                    "gate4": "approved",
                    "gate5": "not_ready",
                },
                "decisions": [],
                "artifacts": {},
                "blockers": [],
                "cache_summary": {},
            }
        )
        atomic_write_json(
            self.root / "reconstruction_timeline.json",
            {
                "artifact_type": "reconstruction_timeline",
                "duration_seconds": 4.0,
                "fragments": [],
            },
        )
        atomic_write_json(
            self.root / "material_manifest.json",
            {"artifact_type": "material_manifest", "fragments": []},
        )
        (self.root / "captions.srt").write_text(
            "1\n00:00:00,000 --> 00:00:04,000\n测试\n", encoding="utf-8"
        )

    @staticmethod
    def renderer(*, output_path: Path, **_: object) -> dict[str, object]:
        output_path.write_bytes(b"valid-render")
        return {"encoder": "fixture-renderer"}

    @staticmethod
    def probe(_: Path) -> dict[str, object]:
        return {
            "width": 1080,
            "height": 1920,
            "fps": 60,
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "video_stream_count": 1,
            "audio_stream_count": 1,
            "audio_codec": "aac",
            "audio_sample_rate": 44100,
            "audio_channels": 2,
            "duration_seconds": 4.0,
        }

    def test_render_registers_valid_bundle_and_stops_at_gate5(self) -> None:
        adapter = RenderAdapter(self.store, renderer=self.renderer, media_probe=self.probe)
        bundle = adapter.render_final()

        state = self.store.read_state()
        self.assertEqual(state["gate_status"]["gate5"], "awaiting_user")
        self.assertEqual(state["active_stage"], "final_review")
        self.assertEqual(set(bundle), {
            "remix.mp4",
            "captions.srt",
            "final_validation_report.json",
            "render_report.json",
            "jianying_import_manifest.json",
        })
        self.assertFalse(state["gate_status"]["gate5"] == "approved")
        package = adapter.build_gate5_package(
            created_at="2026-08-15T13:00:00Z"
        )
        self.assertEqual(package["gate_id"], "gate5")
        self.assertEqual(package["state_revision"], state["state_revision"])

    def test_render_refuses_incomplete_gate4_or_invalid_media(self) -> None:
        self.store.update_state(
            lambda state: state
            | {"gate_status": dict(state["gate_status"], gate4_post_generation="awaiting_user")}
        )
        adapter = RenderAdapter(self.store, renderer=self.renderer, media_probe=self.probe)
        with self.assertRaisesRegex(RenderError, "Gate prerequisites"):
            adapter.render_final()
        self.assertFalse((self.root / "remix.mp4").exists())

        self.store.update_state(
            lambda state: state
            | {"gate_status": dict(state["gate_status"], gate4_post_generation="approved")}
        )
        invalid_probe = lambda _: dict(self.probe(self.root), fps=30)
        with self.assertRaisesRegex(RenderError, "60fps"):
            RenderAdapter(
                self.store, renderer=self.renderer, media_probe=invalid_probe
            ).render_final()
        self.assertFalse((self.root / "remix.mp4").exists())

    def test_archive_requires_gate5_and_refuses_manual_contract_pilot(self) -> None:
        adapter = RenderAdapter(self.store, renderer=self.renderer, media_probe=self.probe)
        adapter.render_final()
        final_root = self.root / "final"
        with self.assertRaisesRegex(RenderError, "Gate 5 approval"):
            adapter.archive_approved(final_root=final_root, output_name="final.mp4")
        self.store.update_state(
            lambda state: state
            | {
                "execution_mode": "manual-contract-only",
                "gate_status": dict(state["gate_status"], gate5="approved"),
            }
        )
        with self.assertRaisesRegex(RenderError, "pilot"):
            adapter.archive_approved(final_root=final_root, output_name="final.mp4")


if __name__ == "__main__":
    unittest.main()
