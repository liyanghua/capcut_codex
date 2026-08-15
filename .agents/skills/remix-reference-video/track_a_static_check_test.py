#!/usr/bin/env python3
"""Focused tests for the Track A static guardrail."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = ROOT / ".agents" / "skills" / "remix-reference-video"
CHECKER = SKILL_ROOT / "track_a_static_check.py"


class TrackAStaticCheckTest(unittest.TestCase):
    def run_checker(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(CHECKER), *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            env={"PYTHONDONTWRITEBYTECODE": "1"},
        )

    def test_current_contract_passes_without_media_claim(self) -> None:
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("registry_envelope=passed", result.stdout)
        self.assertIn("trigger_behavior_evaluation=not_run", result.stdout)
        self.assertIn("production_media_comparison=not_run", result.stdout)
        self.assertNotIn("production_media_changed=false", result.stdout)

    def test_duplicate_registry_path_is_rejected(self) -> None:
        registry_path = SKILL_ROOT / "schemas" / "v2-alpha.registry.schema.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp_dir:
            registry["x-artifacts"][1]["path"] = registry["x-artifacts"][0]["path"]
            invalid_registry = Path(temp_dir) / "invalid-registry.json"
            invalid_registry.write_text(
                json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            result = self.run_checker("--registry", str(invalid_registry))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("registry artifact paths must be unique", result.stdout)


if __name__ == "__main__":
    unittest.main()
