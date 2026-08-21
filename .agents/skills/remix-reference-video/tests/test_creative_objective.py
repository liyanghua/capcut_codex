from __future__ import annotations

import unittest

from remix_reference_video.adapters.blueprint import BlueprintAdapter, BlueprintValidationError


class CreativeObjectiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.brief = {
            "approved_claims": [
                {"claim_id": "clear", "text": "极简透明"},
                {"claim_id": "water", "text": "防水防油"},
            ],
            "forbidden_claims": ["治疗"],
            "product": {"name": "透明桌垫", "audience": "精致白领"},
            "target": {"platform": "抖音"},
            "duration_envelope": {
                "minimum_seconds": 10.0,
                "maximum_seconds": 20.0,
                "strength": "soft",
            },
            "creative_objective": {
                "desired_action": "了解产品细节",
                "opening_hook_hypothesis": "先看到透明质感",
                "product_appearance_target_seconds": 3.0,
                "cta": "not_required",
            },
        }

    def test_objective_uses_only_frozen_brief_and_gate1_selection(self) -> None:
        result = BlueprintAdapter().build_creative_objective(
            brief=self.brief,
            selected_decomposition_id="decomp-001",
            gate1_selection_hash="a" * 64,
        )

        self.assertEqual(result["artifact_type"], "creative_objective")
        self.assertEqual(result["product"], "透明桌垫")
        self.assertEqual(result["audience"], "精致白领")
        self.assertEqual(result["platform"], "抖音")
        self.assertEqual(result["approved_claims"], ["极简透明", "防水防油"])
        self.assertEqual(result["forbidden_claims"], ["治疗"])
        self.assertEqual(result["product_appearance_target_seconds"], 3.0)
        self.assertEqual(sum(row["weight"] for row in result["objectives"]), 1.0)
        self.assertIn("project_brief.json", result["input_hashes"])
        self.assertEqual(
            result["input_hashes"]["gate1_decomposition_selection"], "a" * 64
        )

    def test_identity_fields_cannot_be_overridden_and_exception_is_explicit(self) -> None:
        changed = dict(self.brief)
        changed["creative_objective"] = {
            **self.brief["creative_objective"],
            "product": "其他产品",
            "product_appearance_exception": "素材中商品出现受限",
        }
        with self.assertRaisesRegex(BlueprintValidationError, "identity"):
            BlueprintAdapter().build_creative_objective(
                brief=changed,
                selected_decomposition_id="decomp-001",
                gate1_selection_hash="b" * 64,
            )

        explicit_exception = dict(self.brief)
        explicit_exception["creative_objective"] = {
            **self.brief["creative_objective"],
            "product_appearance_exception": "素材中商品出现受限",
        }
        result = BlueprintAdapter().build_creative_objective(
            brief=explicit_exception,
            selected_decomposition_id="decomp-001",
            gate1_selection_hash="b" * 64,
        )
        self.assertEqual(result["product_appearance_exception"], "素材中商品出现受限")

    def test_baseline_fragments_receive_deterministic_visual_intent(self) -> None:
        result = BlueprintAdapter().compile(
            brief={
                **self.brief,
                "maximum_narration_chars_per_second": 5.0,
                "approved_fallbacks": [],
            },
            recipe={"artifact_type": "recipe"},
            coverage_precheck={"artifact_type": "coverage_precheck", "scope": "precheck"},
            target_fragments=[{
                "fragment_id": "fragment01",
                "claim_ids": ["clear"],
                "narration": "极简透明",
                "narrative_role": "产品出现",
                "required_actions": ["show_product"],
                "reference_shot_id": "shot-1",
            }],
        )
        intent = result["content_baseline"]["fragments"][0]["visual_intent"]
        self.assertEqual(intent["reference_shot_ids"], ["shot-1"])
        self.assertEqual(intent["required_actions"], ["show_product"])
        self.assertEqual(intent["claim_ids"], ["clear"])


if __name__ == "__main__":
    unittest.main()
