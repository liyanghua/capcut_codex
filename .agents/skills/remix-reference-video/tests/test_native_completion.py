from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.approvals import ApprovalService
from remix_reference_video.native_completion import register_completion_adapters
from remix_reference_video.native_registry import NativeAdapterRegistry
from remix_reference_video.runner import ProductionRunner
from remix_reference_video.storage import TaskStorage, atomic_write_json


class _Provider:
    provider_id = "fixture-voice"

    def synthesize(self, **_: object) -> bytes:
        return b"voice"


class NativeCompletionTests(unittest.TestCase):
    def test_completion_registry_contains_gate3_to_gate5_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.mkdir(exist_ok=True)
            registry = register_completion_adapters(
                NativeAdapterRegistry(root), asset_root=root,
                voice_provider=_Provider(), voice_duration=lambda _: 1.0,
                proxy_renderer=lambda **_: {"path": "proxy.mp4"},
                boundary_frame_times=lambda _: [],
                final_renderer=lambda **kwargs: _render(kwargs["output_path"]),
                media_probe=lambda _: _media(),
            )
            self.assertEqual(registry.stage_ids(), (
                "build-material-selection-package", "freeze-fragment-plan",
                "validate-script-evidence", "summarize-gate3", "build-production-script",
                "materialize-approved-broad", "voice-preflight", "build-gate4-pre-package", "generate-voice",
                "build-reconstruction-timeline", "build-gate4-post-package", "summarize-gate4", "render-proxy",
                "validate-proxy-boundaries", "render-final", "build-gate5-package",
                "archive-approved",
            ))

    def test_existing_fragment_plan_is_superseded_by_revisioned_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = TaskStorage(root)
            store.initialize_state({"execution_mode":"track-b-production", "run_id":"run-1", "state_revision":0, "active_stage":None, "active_command":None, "stage_status":{}, "gate_status":{}, "decisions":[], "artifacts":{}, "blockers":[], "cache_summary":{}})
            for _ in range(7):
                store.update_state(lambda current: current)
            atomic_write_json(root / "fragment_plan.json", {"artifact_type":"fragment_plan", "lifecycle_status":"approved"})
            registry = register_completion_adapters(
                NativeAdapterRegistry(root), asset_root=root,
                voice_provider=_Provider(), voice_duration=lambda _: 1.0,
                proxy_renderer=lambda **_: {"path": "proxy.mp4"},
                boundary_frame_times=lambda _: [],
                final_renderer=lambda **kwargs: _render(kwargs["output_path"]),
                media_probe=lambda _: _media(),
            )
            output = registry.get("freeze-fragment-plan").declared_outputs()[0]
            self.assertEqual(output.relative_to(root.resolve()).as_posix(), "versions/fragment_plan/r7/fragment_plan.json")

    def test_run_approve_resume_reaches_gate5_and_archives_in_isolated_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            source = assets / "clip.mp4"
            source.write_bytes(b"approved-clip")
            source_hash = _sha256(source)
            (root / "stage_inputs").mkdir()
            baseline = {
                "artifact_type": "content_baseline",
                "claims": [{"claim_id": "clean", "text": "擦净"}],
                "forbidden_claims": [],
                "fragments": [{
                    "fragment_id": "fragment01", "narration": "擦净", "claim_ids": ["clean"],
                    "requirements": {"product_type": "tablemat", "required_semantics": ["proof.clean"],
                        "required_actions": ["wipe"], "allowed_media_types": ["video"],
                        "forbidden_semantics": [], "expected_visual_seconds": 1.0},
                }],
            }
            atomic_write_json(root / "content_baseline.json", baseline)
            atomic_write_json(root / "mutation_plan.json", {"artifact_type": "mutation_plan", "allowed_fallbacks": []})
            atomic_write_json(root / "matches.json", {
                "artifact_type": "matches", "status": "ready", "fragments": [{
                    "fragment_id": "fragment01", "status": "matched", "selected_asset_id": "asset-1",
                    "candidates": [{"asset_id": "asset-1", "source_id": "source-1", "source_path": "clip.mp4",
                        "sha256": source_hash, "perceptual_hash": "phash-1", "confidence": 0.95,
                        "broad_ranges": [{"start_seconds": 0.0, "end_seconds": 2.0}],
                        "duration_seconds": 2.0}],
                }],
            })
            runner = ProductionRunner(root, ())
            runner.initialize(run_id="completion-run")
            store = TaskStorage(root)
            store.update_state(lambda state: state | {
                "stages": {"reference_split": {"status": "approved"}, "content_blueprint": {"status": "approved"}},
                "stage_status": {**state["stage_status"],
                    "split-reference": "succeeded", "index-assets": "succeeded", "build-coverage-precheck": "succeeded",
                    "compile-blueprint": "succeeded", "compile-mutation-plan": "succeeded",
                    "lint-gate2-package": "succeeded", "build-coverage-authoritative": "succeeded", "match-assets": "succeeded"},
                "gate_status": {**state["gate_status"], "gate1": "approved", "gate2": "approved"},
            })
            atomic_write_json(root / "stage_inputs/build-material-selection-package.json", _handoff(
                "build-material-selection-package", {"overlay_decisions": {"fragment01": "no_action"},
                    "range_overrides": {"fragment01": {"start_seconds": 0.25, "end_seconds": 1.5}}}
            ))
            atomic_write_json(root / "stage_inputs/validate-script-evidence.json", _handoff(
                "validate-script-evidence", {"evidence_rows": [{"fragment_id": "fragment01", "voice_text": "擦净",
                    "approved_claim_ids": ["clean"], "closure_decision": "closed"}]}
            ))
            atomic_write_json(root / "stage_inputs/voice-preflight.json", _handoff(
                "voice-preflight", {"provider":"fixture","speaker":"female","speed":1.05}
            ))
            registry = register_completion_adapters(
                NativeAdapterRegistry(root), asset_root=assets, voice_provider=_Provider(),
                voice_duration=lambda _: 1.0, proxy_renderer=lambda **_: {"path": "proxy.mp4"},
                boundary_frame_times=lambda _: [], final_renderer=lambda **kwargs: _render(kwargs["output_path"]),
                media_probe=lambda _: _media(),
            )
            runner = ProductionRunner.from_registry(root, registry)
            approvals: list[str] = []
            for _ in range(40):
                result = runner.run(resume=bool(approvals))
                state = store.read_state()
                pending = next((gate for gate, status in state["gate_status"].items() if status == "awaiting_user"), None)
                if pending is None:
                    if result.status == "succeeded" and state["stage_status"].get("archive-approved") == "succeeded":
                        break
                    continue
                package = root / "gate_review_packages" / f"{pending}.json"
                if not package.is_file():
                    continue
                decision = root / f"decision-{pending}.json"
                strategy = {"overlay_decisions": {"fragment01": "no_action"}}
                if pending == "gate3_evidence_closure":
                    strategy = {}
                if pending == "gate4_pre_generation":
                    strategy = {"tts_settings": {"provider": "fixture", "voice": "female", "speed": 1.05}}
                atomic_write_json(decision, {"decision": "approved", "scope_type": "output_bundle", "scope_ids": [pending], "strategy": strategy})
                ApprovalService(store).approve(
                    gate_id=pending, review_package_hash=_sha256(package), decision_file=decision, actor="fixture-owner"
                )
                approvals.append(pending)
            else:
                self.fail(f"completion chain did not reach archive: active={state.get('active_stage')} gates={state.get('gate_status')} stages={state.get('stage_status')}")
            self.assertEqual(approvals, ["gate3_material_selection", "gate3_evidence_closure", "gate4_pre_generation", "gate4_post_generation", "gate5"])
            duration_report = root / "voice" / "duration_report.json"
            self.assertTrue(duration_report.is_file())
            self.assertEqual(json.loads(duration_report.read_text(encoding="utf-8"))["total_duration_seconds"], 1.0)
            self.assertTrue((root / "gate_review_packages" / "gate5.json").is_file())
            self.assertTrue((root / "final" / "remix.mp4").is_file())
            fragment_plan = json.loads((root / "fragment_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(fragment_plan["fragments"][0]["approved_broad_range"], {"start_seconds": 0.25, "end_seconds": 1.5})
            self.assertEqual(json.loads((root / "voice_preflight.json").read_text(encoding="utf-8"))["speed"], 1.05)


def _handoff(stage_id: str, payload: dict[str, object]) -> dict[str, object]:
    return {"artifact_type": "stage_input", "schema_id": "urn:capcut:remix-reference-video:artifact:stage-input",
        "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1", "skill_version": "2.0.0-alpha.1",
        "stage_id": stage_id, "producer": "fixture", "created_at": "2026-08-16T10:00:00Z",
        "lifecycle_status": "awaiting_user", "input_hashes": {}, "payload": payload}


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _render(path: Path) -> dict[str, object]:
    path.write_bytes(b"final-video")
    return {"encoder": "fixture"}


def _media() -> dict[str, object]:
    return {"width": 1080, "height": 1920, "fps": 60, "video_codec": "h264", "pixel_format": "yuv420p",
        "video_stream_count": 1, "audio_stream_count": 1, "audio_codec": "aac", "audio_sample_rate": 44100,
        "audio_channels": 2, "duration_seconds": 1.0}


if __name__ == "__main__":
    unittest.main()
