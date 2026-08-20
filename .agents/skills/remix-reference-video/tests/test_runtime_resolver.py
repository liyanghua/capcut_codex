from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.runtime_resolver import RuntimeResolver, RuntimeUnavailable
from remix_reference_video.storage import atomic_write_json


class RuntimeResolverTests(unittest.TestCase):
    def test_missing_invalid_and_valid_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            resolver = RuntimeResolver(workspace)
            with self.assertRaises(RuntimeUnavailable):
                resolver.resolve()
            client = workspace / "doubao_client.py"
            client.write_text("# client\n", encoding="utf-8")
            config = workspace / "workbench" / "runtime_config.json"
            atomic_write_json(config, {"python_executable": "relative/python", "doubao_client_script": str(client)})
            with self.assertRaises(RuntimeUnavailable):
                resolver.resolve()
            atomic_write_json(config, {"python_executable": sys.executable, "doubao_client_script": str(client)})
            resolved = resolver.resolve()
            self.assertEqual(resolved.python_executable, Path(sys.executable).resolve())
            self.assertEqual(resolved.doubao_client_script, client)


if __name__ == "__main__":
    unittest.main()
