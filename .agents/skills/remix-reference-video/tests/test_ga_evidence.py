from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.cli import main


class GaEvidenceHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.task = Path(self._temporary.name) / "task"
        self.task.mkdir()
        (self.task / "pipeline_state.json").write_text(
            json.dumps(
                {
                    "run_id": "ga-test",
                    "execution_mode": "manual-contract-only",
                    "state_revision": 0,
                    "gate_status": {
                        "gate1": "awaiting_user",
                        "gate2": "not_started",
                    },
                    "decisions": [],
                }
            ),
            encoding="utf-8",
        )
        (self.task / "recipe.json").write_text('{"recipe": 1}\n', encoding="utf-8")

    def invoke(self, *args: str) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([*args, "--json"])
        return code, json.loads(output.getvalue())

    def test_prepare_review_writes_package_without_touching_state(self) -> None:
        before = (self.task / "pipeline_state.json").read_bytes()
        code, payload = self.invoke(
            "ga-prepare-review",
            "--task-dir",
            str(self.task),
            "--gate",
            "gate1",
            "--artifact",
            "recipe.json",
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["gate_id"], "gate1")
        self.assertEqual(before, (self.task / "pipeline_state.json").read_bytes())
        self.assertTrue((self.task / "gate_review_packages/gate1.json").is_file())

    def test_record_decision_requires_current_review_package_and_structured_file(self) -> None:
        self.invoke(
            "ga-prepare-review",
            "--task-dir",
            str(self.task),
            "--gate",
            "gate1",
            "--artifact",
            "recipe.json",
        )
        decision = self.task / "decision.json"
        decision.write_text(
            json.dumps(
                {
                    "decision": "approved",
                    "scope_type": "artifact_set",
                    "scope_ids": ["recipe.json"],
                    "directives": {},
                }
            ),
            encoding="utf-8",
        )
        code, payload = self.invoke(
            "ga-record-decision",
            "--task-dir",
            str(self.task),
            "--gate",
            "gate1",
            "--review-package",
            "gate_review_packages/gate1.json",
            "--decision-file",
            "decision.json",
            "--actor",
            "operator@example.test",
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["decision"], "approved")
        state = json.loads((self.task / "pipeline_state.json").read_text())
        self.assertEqual(state["gate_status"]["gate1"], "approved")
        self.assertEqual(state["state_revision"], 1)

    def test_audit_is_write_free_and_detects_changed_input(self) -> None:
        self.invoke(
            "ga-prepare-review",
            "--task-dir",
            str(self.task),
            "--gate",
            "gate1",
            "--artifact",
            "recipe.json",
        )
        before = (self.task / "pipeline_state.json").read_bytes()
        (self.task / "recipe.json").write_text('{"recipe": 2}\n', encoding="utf-8")
        code, payload = self.invoke("ga-audit", "--task-dir", str(self.task))
        self.assertEqual(code, 5)
        self.assertTrue(any("hash" in error for error in payload["errors"]))
        self.assertEqual(before, (self.task / "pipeline_state.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
