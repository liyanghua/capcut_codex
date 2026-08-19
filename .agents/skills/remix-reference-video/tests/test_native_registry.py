from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.native_registry import (
    NativeAdapterRegistry,
    NativeRegistryError,
    NativeStageAdapter,
)
from remix_reference_video.native_planning import register_planning_adapters
from remix_reference_video.runner import ProductionRunner
from remix_reference_video.storage import TaskStorage


class NativeRegistryTests(unittest.TestCase):
    def test_registry_exposes_unique_dag_bound_adapters_in_execution_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = NativeAdapterRegistry(root)
            registry.register(
                NativeStageAdapter(
                    root,
                    execution_stage_id="compile-blueprint",
                    implementation_version="test-v1",
                    required_inputs=(root / "recipe.json",),
                    declared_outputs=(root / "shot_blueprint.json",),
                    execute_fn=lambda: {"artifact_type": "shot_blueprint"},
                )
            )
            self.assertEqual(registry.stage_ids(), ("compile-blueprint",))
            self.assertEqual(registry.adapters(), (registry.get("compile-blueprint"),))

    def test_registry_rejects_duplicate_or_unknown_dag_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = NativeAdapterRegistry(root)
            adapter = NativeStageAdapter(
                root,
                execution_stage_id="compile-blueprint",
                implementation_version="test-v1",
                required_inputs=(),
                declared_outputs=(root / "out.json",),
                execute_fn=lambda: {},
            )
            registry.register(adapter)
            with self.assertRaises(NativeRegistryError):
                registry.register(adapter)
            with self.assertRaises(NativeRegistryError):
                registry.register(
                    NativeStageAdapter(
                        root,
                        execution_stage_id="not-a-dag-node",
                        implementation_version="test-v1",
                        required_inputs=(),
                        declared_outputs=(),
                        execute_fn=lambda: {},
                    )
                )

    def test_required_stage_input_cannot_be_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = NativeStageAdapter(
                root,
                execution_stage_id="compile-blueprint",
                implementation_version="test-v1",
                required_inputs=(),
                declared_outputs=(root / "out.json",),
                execute_fn=lambda payload: payload,
                require_stage_input=True,
            )
            with self.assertRaisesRegex(NativeRegistryError, "stage input is required"):
                adapter.execute(attempt_id="attempt-1")

    def test_native_adapter_supports_sidecar_text_and_domain_managed_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            timeline = root / "reconstruction_timeline.json"
            captions = root / "captions.srt"
            adapter = NativeStageAdapter(
                root,
                execution_stage_id="build-reconstruction-timeline",
                implementation_version="test-v1",
                required_inputs=(),
                declared_outputs=(timeline, captions),
                execute_fn=lambda: {
                    "reconstruction_timeline": {"artifact_type": "reconstruction_timeline"},
                    "captions_srt": "1\n00:00:00,000 --> 00:00:01,000\n测试\n",
                },
            )
            adapter.execute(attempt_id="attempt-1")
            self.assertIn("测试", captions.read_text(encoding="utf-8"))

            binary = root / "remix.mp4"
            managed = NativeStageAdapter(
                root,
                execution_stage_id="render-final",
                implementation_version="test-v1",
                required_inputs=(),
                declared_outputs=(binary,),
                execute_fn=lambda: (binary.write_bytes(b"video"), {"status": "rendered"})[1],
                domain_managed_outputs=True,
            )
            managed.execute(attempt_id="attempt-2")
            self.assertEqual(binary.read_bytes(), b"video")

    def test_native_adapter_executes_from_stage_input_and_writes_declared_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handoff = root / "stage_inputs" / "compile-blueprint.json"
            handoff.parent.mkdir()
            handoff.write_text(
                json.dumps({
                    "artifact_type": "stage_input",
                    "schema_id": "urn:capcut:remix-reference-video:artifact:stage-input",
                    "schema_version": "1.0.0",
                    "contract_version": "2.0.0-alpha.1",
                    "skill_version": "2.0.0-alpha.1",
                    "stage_id": "compile-blueprint",
                    "producer": "fixture",
                    "created_at": "2026-08-16T10:00:00Z",
                    "lifecycle_status": "awaiting_user",
                    "input_hashes": {},
                    "payload": {"value": "from-handoff"},
                }),
                encoding="utf-8",
            )
            output = root / "shot_blueprint.json"
            adapter = NativeStageAdapter(
                root,
                execution_stage_id="compile-blueprint",
                implementation_version="test-v1",
                required_inputs=(),
                declared_outputs=(output,),
                execute_fn=lambda payload: {"artifact_type": "shot_blueprint", **payload},
            )
            result = adapter.execute(attempt_id="attempt-1")
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["value"], "from-handoff")
            initial = adapter.cache_fingerprint()
            value = json.loads(handoff.read_text(encoding="utf-8"))
            value["payload"]["value"] = "changed"
            handoff.write_text(json.dumps(value), encoding="utf-8")
            self.assertNotEqual(initial, adapter.cache_fingerprint())

    def test_registry_can_build_the_real_production_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = NativeAdapterRegistry(root)
            registry.register(
                NativeStageAdapter(
                    root,
                    execution_stage_id="compile-blueprint",
                    implementation_version="test-v1",
                    required_inputs=(),
                    declared_outputs=(root / "blueprint.json",),
                    execute_fn=lambda: {"artifact_type": "shot_blueprint"},
                )
            )
            runner = ProductionRunner.from_registry(root, registry)
            self.assertEqual(tuple(runner.adapters), ("compile-blueprint",))

    def test_planning_registry_calls_real_blueprint_adapter_from_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "stage_inputs").mkdir()
            (root / "project_brief.json").write_text(json.dumps({
                "approved_claims": [{"claim_id": "clean", "text": "擦净"}],
                "approved_fallbacks": [], "forbidden_claims": [],
                "duration_envelope": {"minimum_seconds": 1, "maximum_seconds": 3, "strength": "soft"},
                "maximum_narration_chars_per_second": 5,
            }), encoding="utf-8")
            (root / "recipe.json").write_text(json.dumps({"artifact_type": "recipe"}), encoding="utf-8")
            (root / "coverage_precheck.json").write_text(json.dumps({
                "artifact_type": "coverage_precheck", "scope": "precheck"
            }), encoding="utf-8")
            (root / "asset_profiles.json").write_text(json.dumps({"asset_profiles": []}), encoding="utf-8")
            (root / "pipeline_state.json").write_text(json.dumps({"gate_status": {"gate2": "not_ready"}}), encoding="utf-8")
            (root / "stage_inputs" / "compile-blueprint.json").write_text(json.dumps({
                "artifact_type": "stage_input",
                "schema_id": "urn:capcut:remix-reference-video:artifact:stage-input",
                "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1",
                "skill_version": "2.0.0-alpha.1", "stage_id": "compile-blueprint",
                "producer": "fixture", "created_at": "2026-08-16T10:00:00Z",
                "lifecycle_status": "awaiting_user", "input_hashes": {},
                "payload": {"target_fragments": [{"fragment_id": "fragment01", "claim_ids": ["clean"], "narration": "擦净", "narrative_role": "功能证明", "required_actions": ["demonstrate_feature"]}]}
            }), encoding="utf-8")
            registry = register_planning_adapters(
                NativeAdapterRegistry(root),
                brief_path=root / "project_brief.json",
                recipe_path=root / "recipe.json",
                coverage_precheck_path=root / "coverage_precheck.json",
                asset_profiles_path=root / "asset_profiles.json",
            )
            result = registry.get("compile-blueprint").execute(attempt_id="attempt-1")
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(json.loads((root / "content_baseline.json").read_text())["artifact_type"], "content_baseline")

    def test_native_registry_adapter_runs_through_production_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "stage_inputs").mkdir()
            output = root / "runner-output.json"
            registry = NativeAdapterRegistry(root)
            registry.register(NativeStageAdapter(
                root,
                execution_stage_id="compile-blueprint",
                implementation_version="test-v1",
                required_inputs=(),
                declared_outputs=(output,),
                execute_fn=lambda: {"artifact_type": "shot_blueprint"},
            ))
            runner = ProductionRunner.from_registry(root, registry)
            runner.initialize(run_id="native-run")
            store = TaskStorage(root)
            store.update_state(lambda state: state | {
                "gate_status": {**state["gate_status"], "gate1": "approved"},
                "stage_status": {**state["stage_status"],
                    "split-reference": "succeeded",
                    "index-assets": "succeeded",
                    "build-coverage-precheck": "succeeded"},
            })
            result = runner.run()
            self.assertEqual(result.status, "succeeded")
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
