from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.adapters.script_compile import (
    ProductionScriptCompiler,
    ScriptCompileError,
)
from remix_reference_video.storage import atomic_write_json


class ProductionScriptCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.baseline = {
            "artifact_type": "content_baseline",
            "claims": [{"claim_id": "clean", "text": "污渍可以擦净"}],
            "forbidden_claims": ["绝对防水"],
            "narrative_contract_version": "narrative_contract_v1",
            "fragments": [
                {
                    "fragment_id": "fragment01",
                    "narration": "污渍可以擦净",
                    "claim_ids": ["clean"],
                }
            ],
        }
        self.mutation = {
            "artifact_type": "mutation_plan",
            "allowed_fallbacks": [
                {
                    "fallback_id": "clean-observed",
                    "claim_id": "clean",
                    "text": "擦拭后表面恢复干净",
                }
            ],
        }
        self.evidence = {
            "artifact_type": "script_evidence_matrix",
            "lifecycle_status": "approved",
            "rows": [
                {
                    "fragment_id": "fragment01",
                    "voice_text": "污渍可以擦净",
                    "approved_claim_ids": ["clean"],
                    "selected_candidate_id": "fragment01:c1",
                    "closure_decision": "closed",
                    "fallback": None,
                }
            ],
        }

    def write_inputs(self) -> tuple[Path, Path, Path]:
        baseline = self.root / "content_baseline.json"
        mutation = self.root / "mutation_plan.json"
        evidence = self.root / "script_evidence_matrix.json"
        atomic_write_json(baseline, self.baseline)
        atomic_write_json(mutation, self.mutation)
        atomic_write_json(evidence, self.evidence)
        return baseline, mutation, evidence

    def write_narrative(self, status: str = "passed") -> Path:
        report = {
            "artifact_type": "narrative_coherence_report",
            "schema_id": "urn:capcut:remix-reference-video:artifact:narrative-coherence-report",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "implementation_version": "narrative-coherence-v1",
            "lifecycle_status": "ready",
            "input_hashes": {"content_baseline.json": "a" * 64},
            "status": status,
            "narrative_contract_version": "narrative_contract_v1",
            "continuity_lexicon_version": "continuity_lexicon_v1",
            "fragments": [
                {
                    "fragment_id": "fragment01",
                    "narrative_role": "功能证明",
                    "required_actions": ["demonstrate_feature"],
                    "continuity_before": None,
                    "continuity_after": None,
                    "approved_claim_ids": ["clean"],
                    "evidence_row_ref": "fragment01",
                    "coherence_status": "passed",
                    "blocked_reasons": [],
                    "business_explanation": "",
                }
            ],
            "checks": {"opening_context": "passed", "transition_coverage": "passed", "claim_density": "passed", "closing": "passed"},
            "blocked_fragment_ids": [],
            "allowed_resolutions": [],
        }
        path = self.root / "narrative_coherence_report.json"
        atomic_write_json(path, report)
        return path

    def compile(self) -> dict[str, object]:
        baseline, mutation, evidence = self.write_inputs()
        narrative = self.write_narrative()
        with evidence.open("rb") as stream:
            evidence_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        return ProductionScriptCompiler().compile(
            content_baseline_path=baseline,
            mutation_plan_path=mutation,
            evidence_matrix_path=evidence,
            evidence_approval_record={
                "gate_id": "gate3_evidence_closure",
                "decision": "approved",
                "input_hashes": {"script_evidence_matrix.json": evidence_hash},
            },
            narrative_report_path=narrative,
        )

    def test_compiles_candidate_with_actual_input_hashes_only(self) -> None:
        candidate = self.compile()

        self.assertEqual(candidate["artifact_type"], "production_script_candidate")
        self.assertEqual(candidate["lifecycle_status"], "awaiting_user")
        self.assertEqual(candidate["lines"][0]["text"], "污渍可以擦净")
        self.assertNotIn("tts_settings", candidate)
        self.assertFalse((self.root / "approved_production_script.json").exists())
        for name, expected in candidate["input_hashes"].items():
            with (self.root / name).open("rb") as stream:
                self.assertEqual(expected, hashlib.file_digest(stream, "sha256").hexdigest())

    def test_missing_or_unapproved_evidence_blocks_compilation(self) -> None:
        self.evidence["rows"] = []
        with self.assertRaisesRegex(ScriptCompileError, "missing closed evidence"):
            self.compile()
        baseline, mutation, evidence = self.write_inputs()
        narrative = self.write_narrative()
        with self.assertRaisesRegex(ScriptCompileError, "must be approved"):
            ProductionScriptCompiler().compile(
                content_baseline_path=baseline,
                mutation_plan_path=mutation,
                evidence_matrix_path=evidence,
                evidence_approval_record={
                    "gate_id": "gate3_evidence_closure",
                    "decision": "rejected",
                    "input_hashes": {},
                },
                narrative_report_path=narrative,
            )

    def test_blocked_or_manual_narrative_report_prevents_compilation(self) -> None:
        for status in ("blocked", "manual_review"):
            with self.subTest(status=status):
                baseline, mutation, evidence = self.write_inputs()
                narrative = self.write_narrative(status)
                with self.assertRaisesRegex(ScriptCompileError, "narrative coherence gate"):
                    ProductionScriptCompiler().compile(
                        content_baseline_path=baseline,
                        mutation_plan_path=mutation,
                        evidence_matrix_path=evidence,
                        evidence_approval_record={
                            "gate_id": "gate3_evidence_closure",
                            "decision": "approved",
                            "input_hashes": {"script_evidence_matrix.json": "a" * 64},
                        },
                        narrative_report_path=narrative,
                    )

    def test_approved_fallback_is_selected_exactly(self) -> None:
        self.evidence["rows"][0]["fallback"] = {"fallback_id": "clean-observed"}
        self.evidence["rows"][0]["voice_text"] = ""

        candidate = self.compile()

        self.assertEqual(candidate["lines"][0]["text"], "擦拭后表面恢复干净")
        self.assertEqual(candidate["lines"][0]["fallback_id"], "clean-observed")

    def test_unapproved_fallback_and_claim_strengthening_are_rejected(self) -> None:
        self.evidence["rows"][0]["fallback"] = {"fallback_id": "invented"}
        with self.assertRaisesRegex(ScriptCompileError, "unapproved fallback"):
            self.compile()
        self.evidence["rows"][0]["fallback"] = None
        self.evidence["rows"][0]["approved_claim_ids"] = ["absolute-waterproof"]
        self.evidence["rows"][0]["voice_text"] = "绝对防水"
        with self.assertRaisesRegex(ScriptCompileError, "claim boundary"):
            self.compile()


if __name__ == "__main__":
    unittest.main()
