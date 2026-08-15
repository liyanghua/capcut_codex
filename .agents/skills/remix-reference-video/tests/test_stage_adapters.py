from __future__ import annotations

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
