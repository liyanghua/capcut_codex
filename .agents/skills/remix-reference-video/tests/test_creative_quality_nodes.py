from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.adapters.enhancement import EnhancementAdapter
from remix_reference_video.adapters.final_diagnostic import FinalContentDiagnosticAdapter
from remix_reference_video.adapters.shot_quality import ShotQualityAdapter


class CreativeQualityNodeTests(unittest.TestCase):
    def test_shot_quality_blocks_missing_required_action_and_preserves_manual_review(self):
        report = ShotQualityAdapter().build(
            script={"lines": [{"fragment_id": "f1", "required_actions": ["wipe"]}]},
            timeline={"fragments": [{"fragment_id": "f1", "timeline_start_seconds": 0, "timeline_end_seconds": 1}]},
            material={"fragments": [{"fragment_id": "f1", "source_path": "material/f1.mp4"}]},
            proxy={"shots": [{"shot_id": "f1", "action_results": [{"action_id": "wipe", "status": "blocked"}], "continuity": "manual_review"}]},
        )
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["shots"][0]["earliest_recovery_gate"], "gate3_material_selection")
        self.assertEqual(report["shots"][0]["consistency"], "manual_review")

    def test_final_diagnostic_marks_subjective_issue_manual_review(self):
        report = FinalContentDiagnosticAdapter().build(
            shot_quality={"status": "manual_review", "shots": [{"shot_id": "f1", "status": "manual_review", "consistency": "manual_review"}]},
            objective={"objectives": [{"objective_id": "hook", "required": True, "weight": 1.0}]},
        )
        self.assertEqual(report["status"], "manual_review")
        self.assertEqual(report["checks"][0]["status"], "manual_review")

    def test_enhancement_isolated_and_adoption_returns_gate3(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp4"
            source.write_bytes(b"source")
            result = EnhancementAdapter(root).propose(
                shot_id="f1", objective_id="proof", source_materials=[source], modification_intent="强化擦拭动作"
            )
            self.assertEqual(result["status"], "ready")
            self.assertTrue((root / "enhancement_candidates" / "f1").is_dir())
            adopted = EnhancementAdapter(root).adopt(result["candidates"][0]["candidate_id"], result)
            self.assertEqual(adopted["earliest_recovery_gate"], "gate3_material_selection")
            self.assertIn("gate3_evidence_closure", adopted["stale_gates"])


if __name__ == "__main__":
    unittest.main()
