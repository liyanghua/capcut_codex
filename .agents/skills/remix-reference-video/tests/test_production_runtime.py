from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from remix_reference_video.native_registry import NativeAdapterRegistry
from remix_reference_video.orchestrator import default_dag
from remix_reference_video.production_runtime import (
    build_real_registry,
    register_real_completion_adapters,
)


class ProductionRuntimeTests(unittest.TestCase):
    def test_real_runtime_registers_gate3_through_gate5(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            client = root / "tts_client.py"
            client.write_text("# fixture", encoding="utf-8")
            registry = register_real_completion_adapters(
                NativeAdapterRegistry(root),
                asset_root=assets,
                doubao_client_script=client,
            )
            self.assertIn("generate-voice", registry.stage_ids())
            self.assertIn("render-final", registry.stage_ids())
            self.assertIn("build-gate5-package", registry.stage_ids())

    def test_full_real_registry_covers_every_production_node(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            for name, value in (
                ("reference.mp4", b"video"),
                ("project_brief.json", b"{}"),
                ("asset_profiles.json", b'{"asset_profiles":[]}'),
                ("tts_client.py", b"# fixture"),
            ):
                (root / name).write_bytes(value)
            registry = build_real_registry(
                task_root=root,
                reference_path=root / "reference.mp4",
                asset_root=assets,
                brief_path=root / "project_brief.json",
                asset_profiles_path=root / "asset_profiles.json",
                cache_path=root / "cache" / "assets.sqlite3",
                doubao_client_script=root / "tts_client.py",
            )
            expected = tuple(
                node.node_id for node in default_dag() if node.node_id != "init"
            )
            self.assertEqual(registry.stage_ids(), expected)


if __name__ == "__main__":
    unittest.main()
