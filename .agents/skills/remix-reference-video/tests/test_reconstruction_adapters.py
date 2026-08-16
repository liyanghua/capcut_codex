from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.adapters.reconstruction import ReconstructionAdapter
from remix_reference_video.storage import atomic_write_json


class ReconstructionAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.task = self.root / "task"
        self.assets = self.root / "assets"
        self.task.mkdir()
        self.assets.mkdir()

    def test_materializes_by_copy_and_records_source_and_copy_hashes(self) -> None:
        source = self.assets / "clip.mp4"
        source.write_bytes(b"approved-source")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        plan = self.task / "fragment_plan.json"
        atomic_write_json(
            plan,
            {
                "artifact_type": "fragment_plan",
                "lifecycle_status": "approved",
                "fragments": [
                    {
                        "fragment_id": "fragment01",
                        "source_path": "clip.mp4",
                        "source_sha256": source_hash,
                        "approved_broad_range": {
                            "start_seconds": 0.5,
                            "end_seconds": 2.5,
                        },
                    }
                ],
            },
        )

        manifest = ReconstructionAdapter(self.task, self.assets).materialize_approved_broad(
            fragment_plan_path=plan
        )

        copied = self.task / manifest["fragments"][0]["material_path"]
        self.assertEqual(copied.read_bytes(), b"approved-source")
        self.assertEqual(source.read_bytes(), b"approved-source")
        self.assertEqual(manifest["fragments"][0]["copy_mode"], "full_source_copy")
        self.assertEqual(manifest["fragments"][0]["material_sha256"], source_hash)

    def test_source_hash_mismatch_blocks_before_material_copy(self) -> None:
        (self.assets / "clip.mp4").write_bytes(b"changed")
        plan = self.task / "fragment_plan.json"
        atomic_write_json(
            plan,
            {
                "artifact_type": "fragment_plan",
                "lifecycle_status": "approved",
                "fragments": [
                    {
                        "fragment_id": "fragment01",
                        "source_path": "clip.mp4",
                        "source_sha256": "0" * 64,
                        "approved_broad_range": {"start_seconds": 0.0, "end_seconds": 1.0},
                    }
                ],
            },
        )

        with self.assertRaisesRegex(ValueError, "source hash mismatch"):
            ReconstructionAdapter(self.task, self.assets).materialize_approved_broad(
                fragment_plan_path=plan
            )
        self.assertFalse((self.task / "material").exists())


if __name__ == "__main__":
    unittest.main()
