from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.adapters.asset_index import AssetIndexAdapter
from remix_reference_video.adapters.reference_split import ReferenceSplitAdapter
from remix_reference_video.storage import StorageError


class StageAdapterManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.task = self.root / "task"
        self.assets = self.root / "assets"
        self.cache = self.root / "cache"
        self.task.mkdir()
        self.assets.mkdir()
        self.reference = self.task / "reference-2026-08-15.mp4"
        self.reference.write_bytes(b"reference-v1")
        (self.assets / "product.mp4").write_bytes(b"asset-v1")

    def test_reference_split_declares_gate1_manifest_and_content_fingerprint(self) -> None:
        adapter = ReferenceSplitAdapter(self.task, self.reference)

        self.assertEqual(adapter.execution_stage_id, "split-reference")
        self.assertEqual(adapter.required_inputs(), (self.reference,))
        self.assertEqual(adapter.required_gates(), ())
        self.assertEqual(adapter.stop_gate, "gate1")
        self.assertEqual(
            adapter.declared_outputs(),
            (
                self.task / "recipe.json",
                self.task / "video_clips",
                self.task / "review_contact_sheet.jpg",
                self.task / "gate_review_packages/gate1.json",
            ),
        )
        self.assertTrue(adapter.implementation_version)
        initial = adapter.cache_fingerprint()
        self.reference.write_bytes(b"reference-v2")
        self.assertNotEqual(initial, adapter.cache_fingerprint())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
    def test_reference_split_executes_deterministically_and_preserves_source(self) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=160x240:r=10:d=0.6",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=160x240:r=10:d=0.6",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=44100:duration=1.2",
                "-filter_complex",
                "[0:v][1:v]concat=n=2:v=1:a=0[outv]",
                "-map",
                "[outv]",
                "-map",
                "2:a",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-pix_fmt",
                "yuv420p",
                str(self.reference),
            ],
            check=True,
        )
        source_before = self.reference.read_bytes()
        adapter = ReferenceSplitAdapter(self.task, self.reference, scene_threshold=0.2)

        first = adapter.execute(attempt_id="attempt-1")
        evidence_before = {
            path.relative_to(self.task).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.task.rglob("*")
            if path.is_file() and path != self.reference
        }
        resumed = adapter.execute(attempt_id="attempt-2")

        recipe = json.loads((self.task / "recipe.json").read_text(encoding="utf-8"))
        self.assertEqual(recipe["artifact_type"], "recipe")
        self.assertEqual(recipe["schema_version"], "1.0.0")
        self.assertEqual(recipe["reference_video"]["sha256"], hashlib.sha256(source_before).hexdigest())
        self.assertGreaterEqual(len(recipe["shots"]), 2)
        self.assertTrue(all((self.task / row["clip_path"]).is_file() for row in recipe["shots"]))
        self.assertTrue(all((self.task / row["keyframe_path"]).is_file() for row in recipe["shots"]))
        self.assertTrue((self.task / "review_contact_sheet.jpg").is_file())
        self.assertTrue((self.task / "voice/reference-audio.m4a").is_file())
        self.assertTrue((self.task / "gate_review_packages/gate1.json").is_file())
        self.assertEqual(first["status"], "succeeded")
        self.assertEqual(first["stop_gate"], "gate1")
        self.assertEqual(resumed["status"], "cache_hit")
        self.assertEqual(self.reference.read_bytes(), source_before)
        self.assertEqual(
            evidence_before,
            {
                path.relative_to(self.task).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.task.rglob("*")
                if path.is_file() and path != self.reference
            },
        )

    def test_reference_split_rejects_missing_and_symlink_inputs(self) -> None:
        with self.assertRaisesRegex(StorageError, "reference input"):
            ReferenceSplitAdapter(self.task, self.task / "missing.mp4")
        link = self.task / "reference-link.mp4"
        link.symlink_to(self.reference)
        with self.assertRaisesRegex(StorageError, "symlink"):
            ReferenceSplitAdapter(self.task, link)

    def test_asset_index_declares_shared_output_without_a_gate(self) -> None:
        database = self.cache / "assets.sqlite3"
        adapter = AssetIndexAdapter(self.task, self.assets, database)

        self.assertEqual(adapter.execution_stage_id, "index-assets")
        self.assertEqual(adapter.required_inputs(), (self.assets,))
        self.assertEqual(adapter.required_gates(), ())
        self.assertIsNone(adapter.stop_gate)
        self.assertEqual(adapter.declared_outputs(), (database,))
        self.assertTrue(adapter.implementation_version)
        initial = adapter.cache_fingerprint()
        (self.assets / "product.mp4").write_bytes(b"asset-v2")
        self.assertNotEqual(initial, adapter.cache_fingerprint())

    def test_asset_index_adapter_executes_incrementally_without_changing_source(self) -> None:
        source = self.assets / "product.mp4"
        original = source.read_bytes()
        database = self.cache / "assets.sqlite3"
        adapter = AssetIndexAdapter(
            self.task,
            self.assets,
            database,
            probe=lambda path, media_type: {"media_type": media_type},
        )

        cold = adapter.execute(attempt_id="attempt-1")
        warm = adapter.execute(attempt_id="attempt-2")

        self.assertEqual(cold["hashed_files"], 1)
        self.assertEqual(warm["cache_hits"], 1)
        self.assertEqual(warm["implementation_version"], "asset-index-v2")
        self.assertEqual(source.read_bytes(), original)

    def test_adapter_manifests_reject_unregistered_or_writable_asset_paths(self) -> None:
        outside_reference = self.root / "outside.mp4"
        outside_reference.write_bytes(b"outside")

        with self.assertRaisesRegex(StorageError, "task root"):
            ReferenceSplitAdapter(self.task, outside_reference)
        with self.assertRaisesRegex(StorageError, "outside asset root"):
            AssetIndexAdapter(
                self.task,
                self.assets,
                self.assets / "cache/assets.sqlite3",
            )


if __name__ == "__main__":
    unittest.main()
