from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.artifact_validator import ArtifactValidator
from remix_reference_video.narrative_coherence import (
    NARRATIVE_CONTRACT_VERSION,
    CONTINUITY_LEXICON_VERSION,
    NarrativeCoherenceBuilder,
    NarrativeCoherenceError,
)
from remix_reference_video.snapshot_schema_validator import SnapshotSchemaValidator
from remix_reference_video.storage import atomic_write_json


class NarrativeCoherenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.builder = NarrativeCoherenceBuilder()

    def fragments(self, roles):
        return [
            {
                "fragment_id": f"fragment{index + 1:02d}",
                "narrative_role": role,
                "required_actions": [{"开场情境": "show_context", "问题/需求": "show_problem", "产品出现": "show_product", "功能证明": "demonstrate_feature", "使用结果": "show_result", "收束": "close"}[role]],
                "narration": f"第{index + 1}段",
                "claim_ids": ["claim-1"] if role in {"产品出现", "功能证明"} else [],
            }
            for index, role in enumerate(roles)
        ]

    def write(self, roles, voice_texts=None, forbidden=()):
        rows = []
        for index, role in enumerate(roles):
            fragment_id = f"fragment{index + 1:02d}"
            rows.append(
                {
                    "fragment_id": fragment_id,
                    "voice_text": (voice_texts or {}).get(fragment_id, f"第{index + 1}段口播"),
                    "approved_claim_ids": ["claim-1"] if role in {"产品出现", "功能证明"} else [],
                    "closure_decision": "closed",
                    "selected_candidate_id": "c1",
                    "fallback": None,
                }
            )
        atomic_write_json(
            self.root / "content_baseline.json",
            {
                "artifact_type": "content_baseline",
                "claims": [{"claim_id": "claim-1", "text": "防滑"}],
                "forbidden_claims": list(forbidden),
                "narrative_contract_version": NARRATIVE_CONTRACT_VERSION,
                "fragments": self.fragments(roles),
            },
        )
        atomic_write_json(self.root / "mutation_plan.json", {"artifact_type": "mutation_plan", "forbidden_claims": [], "allowed_fallbacks": []})
        atomic_write_json(self.root / "shot_blueprint.json", {"artifact_type": "shot_blueprint", "fragments": self.fragments(roles)})
        atomic_write_json(self.root / "script_evidence_matrix.json", {"artifact_type": "script_evidence_matrix", "rows": rows})

    def build(self, roles, **kwargs):
        self.write(roles, **kwargs)
        return self.builder.build(
            content_baseline_path=self.root / "content_baseline.json",
            mutation_plan_path=self.root / "mutation_plan.json",
            shot_blueprint_path=self.root / "shot_blueprint.json",
            evidence_matrix_path=self.root / "script_evidence_matrix.json",
        )

    def test_passed_report_for_coherent_sequence(self) -> None:
        report = self.build(["开场情境", "功能证明", "收束"])
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["narrative_contract_version"], NARRATIVE_CONTRACT_VERSION)
        self.assertEqual(report["continuity_lexicon_version"], CONTINUITY_LEXICON_VERSION)
        self.assertEqual(report["checks"]["opening_context"], "passed")
        self.assertEqual(report["checks"]["closing"], "passed")
        self.assertEqual(report["checks"]["transition_coverage"], "passed")
        self.assertEqual(report["fragments"][0]["continuity_after"], "情境 → 证明")
        self.assertEqual(report["fragments"][1]["continuity_before"], "情境 → 证明")
        SnapshotSchemaValidator().assert_valid(report, "narrative-coherence-report.schema.json")
        path = self.root / "narrative_coherence_report.json"
        atomic_write_json(path, report)
        self.assertTrue(ArtifactValidator(self.root).validate_quality_report(path).valid)

    def test_missing_metadata_produces_manual_review(self) -> None:
        self.write(["开场情境", "功能证明", "收束"])
        baseline = json.loads((self.root / "content_baseline.json").read_text(encoding="utf-8"))
        del baseline["fragments"][1]["narrative_role"]
        atomic_write_json(self.root / "content_baseline.json", baseline)
        report = self.builder.build(
            content_baseline_path=self.root / "content_baseline.json",
            mutation_plan_path=self.root / "mutation_plan.json",
            shot_blueprint_path=self.root / "shot_blueprint.json",
            evidence_matrix_path=self.root / "script_evidence_matrix.json",
        )
        self.assertEqual(report["status"], "manual_review")
        self.assertEqual(report["fragments"][1]["coherence_status"], "manual_review")

    def test_adjacent_pure_claims_block(self) -> None:
        report = self.build(["产品出现", "功能证明"])
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["checks"]["claim_density"], "blocked")
        self.assertTrue(any("纯卖点" in reason for row in report["fragments"] for reason in row["blocked_reasons"]))

    def test_missing_opening_or_closing_blocks(self) -> None:
        no_opening = self.build(["功能证明", "使用结果", "收束"])
        self.assertEqual(no_opening["checks"]["opening_context"], "blocked")
        self.assertEqual(no_opening["status"], "blocked")
        no_closing = self.build(["开场情境", "功能证明", "使用结果"])
        self.assertEqual(no_closing["checks"]["closing"], "blocked")
        self.assertEqual(no_closing["status"], "blocked")

    def test_unknown_transition_blocks(self) -> None:
        report = self.build(["收束", "开场情境"])
        self.assertEqual(report["checks"]["transition_coverage"], "blocked")
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("缺少承接" in reason for row in report["fragments"] for reason in row["blocked_reasons"]))

    def test_forbidden_claim_text_blocks(self) -> None:
        report = self.build(["开场情境", "功能证明", "收束"], voice_texts={"fragment02": "绝对防水，永不进水"}, forbidden=["绝对防水"])
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("禁用声明" in reason for row in report["fragments"] for reason in row["blocked_reasons"]))

    def test_repeated_builds_are_byte_identical(self) -> None:
        first = self.build(["开场情境", "功能证明", "收束"])
        second = self.build(["开场情境", "功能证明", "收束"])
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, sort_keys=True),
            json.dumps(second, ensure_ascii=False, sort_keys=True),
        )

    def test_invalid_artifact_inputs_are_rejected(self) -> None:
        self.write(["开场情境", "收束"])
        atomic_write_json(self.root / "mutation_plan.json", {"artifact_type": "wrong"})
        with self.assertRaises(NarrativeCoherenceError):
            self.builder.build(
                content_baseline_path=self.root / "content_baseline.json",
                mutation_plan_path=self.root / "mutation_plan.json",
                shot_blueprint_path=self.root / "shot_blueprint.json",
                evidence_matrix_path=self.root / "script_evidence_matrix.json",
            )


if __name__ == "__main__":
    unittest.main()
