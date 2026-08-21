from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from remix_reference_video.change_service import ChangeConflict, ChangeImpactAnalyzer, ChangeService, WorkbenchOrchestrator
from remix_reference_video.review_session import ReviewSessionService
from remix_reference_video.run_registry import RunRegistry
from remix_reference_video.storage import StorageError, TaskStorage, atomic_write_json, read_json_object
from tests.frozen_run_fixture import write_frozen_run_fixture


class ChangeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(); self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve(); (self.root / "gate_review_packages").mkdir()
        self.store = TaskStorage(self.root)
        gates = {"gate1":"approved","gate2":"approved","gate3_material_selection":"awaiting_user","gate3_evidence_closure":"not_ready","gate3":"awaiting_user","gate4_pre_generation":"not_ready","gate4_post_generation":"not_ready","gate4":"not_ready","gate5":"not_ready"}
        self.store.initialize_state({"execution_mode":"track-b-production","run_id":"run-1","state_revision":0,"active_stage":"build-material-selection-package","active_command":None,"stage_status":{"build-production-script":"succeeded","voice-preflight":"succeeded"},"gate_status":gates,"decisions":[],"artifacts":{},"blockers":[],"cache_summary":{}})
        atomic_write_json(self.root / "gate_review_packages/gate3_material_selection.json", {"gate_id":"gate3_material_selection","run_id":"run-1","state_revision":0,"created_at":"2026-08-17T10:00:00Z","input_hashes":{},"policy_version":"policy-v1","runtime_profile":"local-cpu"})
        atomic_write_json(self.root / "fragment_plan.json", {"fragments":[{"fragment_id":"fragment01","approved_broad_range":{"start_seconds":1.0,"end_seconds":5.0}}]})
        atomic_write_json(self.root / "matches.json", {"fragments":[{"fragment_id":"fragment01","candidates":[{"asset_id":"c1","sha256":"a"*64}]}]})
        atomic_write_json(self.root / "content_baseline.json", {"claims":[{"claim_id":"claim01","text":"防水防油"}],"fragments":[{"fragment_id":"fragment01"}]})
        atomic_write_json(self.root / "production_script_candidate.json", {"lines":[{"line_id":"line01","fragment_id":"fragment01","text":"原文案"}]})
        atomic_write_json(self.root / "approved_production_script.json", {"lines":[{"line_id":"line01","fragment_id":"fragment01","text":"原文案"}],"tts_settings":{"provider":"doubao-v3","speaker":"voice-a","speed":1.0},"allowed_tts_settings":{"providers":["doubao-v3"],"speakers":["voice-a","voice-b"],"speed_min":0.9,"speed_max":1.1}})
        atomic_write_json(self.root / "proxy_boundary_report.json", {"boundary_frames":[{"boundary_id":"b01","boundary_seconds":1.0,"status":"passed"}]})
        atomic_write_json(self.root / "stage_inputs/build-material-selection-package.json", {
            "artifact_type":"stage_input","schema_id":"urn:capcut:remix-reference-video:artifact:stage-input","schema_version":"1.0.0","contract_version":"2.0.0-alpha.1","skill_version":"2.0.0-alpha.1",
            "stage_id":"build-material-selection-package","producer":"test","created_at":"2026-08-17T10:00:00Z","lifecycle_status":"awaiting_user","input_hashes":{},"payload":{"overlay_decisions":{"fragment01":"retain_source_text"}}
        })
        self.sessions = ReviewSessionService(self.root, actor="operator-a")
        self.session = self.sessions.open("gate3_material_selection")
        self.analyzer = ChangeImpactAnalyzer(self.root, actor="operator-a")
        self.service = ChangeService(self.root, actor="operator-a")

    def _range(self, start=1.5, end=4.5):
        return {"change_type":"range","scope_ids":["fragment01"],"payload":{"fragment_id":"fragment01","start_seconds":start,"end_seconds":end},"reason":"调整可用画面"}

    def test_preview_binds_fixed_impact_and_rejects_range_escape(self) -> None:
        preview = self.analyzer.preview(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=self._range())
        self.assertEqual(preview["earliest_affected_gate"], "gate3_material_selection")
        self.assertIn("gate5", preview["stale_gates"])
        self.assertTrue(preview["requires_render"])
        self.assertEqual(preview["estimated_machine_seconds"]["measurement_status"], "not_measured")
        self.assertEqual(len(preview["preview_hash"]), 64)
        with self.assertRaisesRegex(ChangeConflict, "range"):
            self.analyzer.preview(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=self._range(0, 8))

    def test_material_overlay_uses_backend_enum_not_ui_alias(self) -> None:
        request = {"change_type":"material","scope_ids":["fragment01"],"payload":{"fragment_id":"fragment01","candidate_id":"c1","source_sha256":"a"*64,"overlay_decision":"keep"},"reason":"替换素材"}
        with self.assertRaises(ChangeConflict):
            self.analyzer.preview(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=request)

    def test_all_eight_change_types_use_fixed_source_allowlists(self) -> None:
        approved_text_sha = hashlib.sha256("原文案".encode()).hexdigest()
        requests = [
            {"change_type":"copy","scope_ids":["line01"],"payload":{"line_ids":["line01"],"text_by_id":{"line01":"新文案"},"edit_intent":"rewrite"},"reason":"优化表达"},
            {"change_type":"claim_scope","scope_ids":["claim01"],"payload":{"claim_ids_add":[],"claim_ids_remove":["claim01"]},"reason":"收窄声明"},
            {"change_type":"voice","scope_ids":[],"payload":{"provider":"doubao-v3","speaker":"voice-b","speed":1.05},"reason":"调整音色"},
            {"change_type":"material","scope_ids":["fragment01"],"payload":{"fragment_id":"fragment01","candidate_id":"c1","source_sha256":"a"*64,"overlay_decision":"retain_source_text"},"reason":"替换素材"},
            self._range(),
            {"change_type":"rerecord","scope_ids":["fragment01"],"payload":{"fragment_ids":["fragment01"],"approved_text_sha256":approved_text_sha},"reason":"重录口播"},
            {"change_type":"boundary","scope_ids":["b01"],"payload":{"boundary_id":"b01","issue_type":"audio_gap"},"reason":"修复边界"},
            {"change_type":"structural","scope_ids":["fragment01"],"payload":{"request_type":"omit","reason":"删去冗余段","affected_ids":["fragment01"]},"reason":"结构调整"},
        ]
        previews = [self.analyzer.preview(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=request) for request in requests]
        self.assertEqual([item["change_type"] for item in previews], [item["change_type"] for item in requests])
        self.assertFalse(previews[-1]["requires_render"])

        invalid = [
            {"change_type":"copy","scope_ids":["line02"],"payload":{"line_ids":["line02"],"text_by_id":{"line02":"越权"}},"reason":"越权"},
            {"change_type":"claim_scope","scope_ids":["claim02"],"payload":{"claim_ids_add":["claim02"],"claim_ids_remove":[]},"reason":"新增声明"},
            {"change_type":"voice","scope_ids":[],"payload":{"provider":"other","speaker":"voice-a","speed":1.0},"reason":"越权"},
            {"change_type":"rerecord","scope_ids":["fragment01"],"payload":{"fragment_ids":["fragment01"],"approved_text_sha256":"b"*64},"reason":"文本不符"},
            {"change_type":"boundary","scope_ids":["b02"],"payload":{"boundary_id":"b02","issue_type":"flash"},"reason":"不存在"},
        ]
        for request in invalid:
            with self.subTest(change_type=request["change_type"]), self.assertRaises(ChangeConflict):
                self.analyzer.preview(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=request)

    def test_estimate_filters_policy_runtime_and_success_samples(self) -> None:
        for seconds in (10.0, 20.0, 40.0):
            self.store.append_metric({"execution_stage_id":"render-final","status":"succeeded","machine_seconds":seconds,"policy_version":"policy-v1","runtime_profile":"local-cpu"})
        self.store.append_metric({"execution_stage_id":"render-final","status":"succeeded","machine_seconds":999.0,"policy_version":"other","runtime_profile":"local-cpu"})
        self.store.append_metric({"execution_stage_id":"render-final","status":"failed","machine_seconds":888.0,"policy_version":"policy-v1","runtime_profile":"local-cpu"})
        request = {"change_type":"boundary","scope_ids":["b01"],"payload":{"boundary_id":"b01","issue_type":"flash"},"reason":"修复闪帧"}

        preview = self.analyzer.preview(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=request)

        estimate = preview["estimated_machine_seconds"]
        self.assertEqual(estimate["measurement_status"], "measured")
        self.assertEqual(estimate["sample_count"], 3)
        self.assertEqual(estimate["p50"], 20.0)
        self.assertEqual(estimate["p90"], 40.0)

    def test_apply_is_atomic_idempotent_and_rejects_stale_preview(self) -> None:
        request = self._range(); preview = self.analyzer.preview(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=request)
        before_plan = (self.root / "fragment_plan.json").read_bytes()
        result = self.service.apply(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=request, preview_hash=preview["preview_hash"], idempotency_key="change-1")
        self.assertTrue(Path(result["change_request_path"]).is_file())
        self.assertTrue(Path(result["job_path"]).is_file())
        self.assertTrue(Path(result["change_override_path"]).is_file())
        self.assertEqual((self.root / "fragment_plan.json").read_bytes(), before_plan)
        self.assertEqual(self.store.read_state()["gate_status"]["gate3_material_selection"], "stale")
        self.assertEqual(result, self.service.apply(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=request, preview_hash=preview["preview_hash"], idempotency_key="change-1"))

        other = tempfile.TemporaryDirectory(); self.addCleanup(other.cleanup)
        # A changed state revision invalidates an uncommitted preview.
        with self.assertRaises(ChangeConflict):
            self.service.apply(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=self._range(2, 3), preview_hash="0"*64, idempotency_key="change-2")

        events = self.store.read_events()
        self.assertLess(
            next(index for index, event in enumerate(events) if event.get("event_type") == "review.change_previewed"),
            next(index for index, event in enumerate(events) if event.get("event_type") == "change.applied"),
        )
        with self.assertRaisesRegex(ChangeConflict, "idempotency"):
            self.service.apply(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=self._range(1.6, 4.4), preview_hash=preview["preview_hash"], idempotency_key="change-1")

    def test_transaction_failure_rolls_back_promotions_and_state(self) -> None:
        request = self._range()
        preview = self.analyzer.preview(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=request)

        with patch("remix_reference_video.change_service.TransactionManager.commit", side_effect=StorageError("injected failure")):
            with self.assertRaisesRegex(StorageError, "injected failure"):
                self.service.apply(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=request, preview_hash=preview["preview_hash"], idempotency_key="rollback-1")

        self.assertEqual(self.store.read_state()["state_revision"], 0)
        self.assertEqual(list((self.root / "change_requests").glob("*.json")) if (self.root / "change_requests").exists() else [], [])
        self.assertEqual(list((self.root / "workbench/jobs").glob("*.json")) if (self.root / "workbench/jobs").exists() else [], [])

    def test_registered_frozen_run_resumes_job_and_restart_replays_result(self) -> None:
        write_frozen_run_fixture(self.root, pair_role="cold")
        RunRegistry(self.root).register(self.root)
        preview = self.analyzer.preview(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=self._range())
        applied = self.service.apply(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=self._range(), preview_hash=preview["preview_hash"], idempotency_key="resume-1")

        calls: list[bool] = []

        class FakeRunner:
            def run(inner_self, *, resume: bool = False):
                calls.append(resume)
                handoff = read_json_object(self.root / "stage_inputs/build-material-selection-package.json")
                self.assertEqual(handoff["payload"]["range_overrides"]["fragment01"], {"start_seconds":1.5,"end_seconds":4.5})
                store = TaskStorage(self.root)
                store.update_state(lambda state: state | {"gate_status": state["gate_status"] | {"gate3_material_selection":"awaiting_user","gate3":"awaiting_user"}})
                return type("Result", (), {"status":"awaiting_user"})()

        orchestrator = WorkbenchOrchestrator(self.root, actor="operator-a", runner_factory=lambda _: FakeRunner())
        result = orchestrator.resume_job(run_id="run-1", job_id=applied["job_id"])
        replay = WorkbenchOrchestrator(self.root, actor="operator-a", runner_factory=lambda _: FakeRunner()).resume_job(run_id="run-1", job_id=applied["job_id"])

        self.assertEqual(calls, [True])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result, replay)
        self.assertEqual(read_json_object(Path(applied["job_path"]))["status"], "completed")
        self.assertEqual(self.store.read_events()[-1]["event_type"], "review.rework_completed")

    def test_resume_rejects_frozen_drift_before_runner_invocation(self) -> None:
        write_frozen_run_fixture(self.root, pair_role="hot")
        RunRegistry(self.root).register(self.root)
        preview = self.analyzer.preview(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=self._range())
        applied = self.service.apply(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=self._range(), preview_hash=preview["preview_hash"], idempotency_key="resume-drift")
        atomic_write_json(self.root / "g_b_frozen_input_snapshot.json", {"artifact_type":"g_b_frozen_input_snapshot","pair_role":"hot","reference_sha256":"d"*64})
        called = False

        def forbidden(_):
            nonlocal called
            called = True
            raise AssertionError("runner must not be built")

        with self.assertRaises(ChangeConflict):
            WorkbenchOrchestrator(self.root, actor="operator-a", runner_factory=forbidden).resume_job(run_id="run-1", job_id=applied["job_id"])
        self.assertFalse(called)

    def test_copy_materialization_is_not_overwritten_by_script_recompile(self) -> None:
        session = self._switch_to_gate4_pre()
        write_frozen_run_fixture(self.root, pair_role="cold")
        RunRegistry(self.root).register(self.root)
        request = {"change_type":"copy","scope_ids":["line01"],"payload":{"line_ids":["line01"],"text_by_id":{"line01":"新文案"},"edit_intent":"rewrite"},"reason":"优化表达"}
        analyzer = ChangeImpactAnalyzer(self.root, actor="operator-a")
        preview = analyzer.preview(session_id=session["session_id"], gate_id="gate4_pre_generation", request=request)
        applied = ChangeService(self.root, actor="operator-a").apply(session_id=session["session_id"], gate_id="gate4_pre_generation", request=request, preview_hash=preview["preview_hash"], idempotency_key="copy-resume")

        class FakeRunner:
            def run(inner_self, *, resume: bool = False):
                state = TaskStorage(self.root).read_state()
                self.assertEqual(state["stage_status"]["build-production-script"], "not_started")
                self.assertEqual(read_json_object(self.root / "production_script_candidate.json")["lines"][0]["text"], "新文案")
                TaskStorage(self.root).update_state(lambda current: current | {"gate_status": current["gate_status"] | {"gate4_pre_generation":"awaiting_user"}})
                return type("Result", (), {"status":"awaiting_user"})()

        result = WorkbenchOrchestrator(self.root, actor="operator-a", runner_factory=lambda _: FakeRunner()).resume_job(run_id="run-1", job_id=applied["job_id"])
        self.assertEqual(result["status"], "completed")

    def test_voice_change_materializes_valid_preflight_handoff(self) -> None:
        session = self._switch_to_gate4_pre()
        write_frozen_run_fixture(self.root, pair_role="hot")
        RunRegistry(self.root).register(self.root)
        request = {"change_type":"voice","scope_ids":[],"payload":{"provider":"doubao-v3","speaker":"voice-b","speed":1.05},"reason":"调整音色"}
        analyzer = ChangeImpactAnalyzer(self.root, actor="operator-a")
        preview = analyzer.preview(session_id=session["session_id"], gate_id="gate4_pre_generation", request=request)
        applied = ChangeService(self.root, actor="operator-a").apply(session_id=session["session_id"], gate_id="gate4_pre_generation", request=request, preview_hash=preview["preview_hash"], idempotency_key="voice-resume")

        class FakeRunner:
            def run(inner_self, *, resume: bool = False):
                handoff = read_json_object(self.root / "stage_inputs/voice-preflight.json")
                self.assertEqual(handoff["payload"], {"provider":"doubao-v3","speaker":"voice-b","speed":1.05})
                TaskStorage(self.root).update_state(lambda current: current | {"gate_status": current["gate_status"] | {"gate4_pre_generation":"awaiting_user"}})
                return type("Result", (), {"status":"awaiting_user"})()

        result = WorkbenchOrchestrator(self.root, actor="operator-a", runner_factory=lambda _: FakeRunner()).resume_job(run_id="run-1", job_id=applied["job_id"])
        self.assertEqual(result["status"], "completed")

    def _switch_to_gate4_pre(self):
        updated = self.store.update_state(lambda state: state | {"active_stage":"build-gate4-pre-package","gate_status": state["gate_status"] | {"gate3_material_selection":"approved","gate3_evidence_closure":"approved","gate3":"approved","gate4_pre_generation":"awaiting_user"}})
        atomic_write_json(self.root / "gate_review_packages/gate4_pre_generation.json", {"gate_id":"gate4_pre_generation","run_id":"run-1","state_revision":updated["state_revision"],"created_at":"2026-08-17T10:01:00Z","input_hashes":{}})
        return ReviewSessionService(self.root, actor="operator-a").open("gate4_pre_generation")

    def test_copy_edit_intent_rejects_merge_and_requires_intent_for_v2(self) -> None:
        merge_request = {"change_type":"copy","scope_ids":["line01"],"payload":{"line_ids":["line01"],"text_by_id":{"line01":"合并"},"edit_intent":"merge"},"reason":"并句"}
        with self.assertRaises(ChangeConflict):
            self.analyzer.validator.validate(self.session["session_id"], "gate3_material_selection", merge_request)
        missing = {"change_type":"copy","scope_ids":["line01"],"payload":{"line_ids":["line01"],"text_by_id":{"line01":"改写"}},"reason":"改写"}
        with self.assertRaisesRegex(ChangeConflict, "edit_intent"):
            self.analyzer.validator.validate(self.session["session_id"], "gate3_material_selection", missing)

    def test_copy_edit_intent_normalizes_missing_intent_only_for_v1_tasks(self) -> None:
        atomic_write_json(self.root / "production_script_candidate.json", {"schema_version":"1.0","lines":[{"line_id":"line01","fragment_id":"fragment01","text":"原文案"}]})
        request = {"change_type":"copy","scope_ids":["line01"],"payload":{"line_ids":["line01"],"text_by_id":{"line01":"改写"}},"reason":"改写"}
        normalized, _ = self.analyzer.validator.validate(self.session["session_id"], "gate3_material_selection", request)
        self.assertEqual(normalized["payload"]["edit_intent"], "rewrite")

    def test_impact_stale_stages_match_dag_downstream_closure(self) -> None:
        from remix_reference_video.change_service import _IMPACTS, dag_downstream_closure

        creative_only = {"build-material-evidence-requirements"}
        for change_type, impact in _IMPACTS.items():
            if not isinstance(impact, dict) or not impact.get("stale_stages"):
                continue
            stages = list(impact["stale_stages"])
            with self.subTest(change_type=change_type):
                self.assertEqual(set(stages) - creative_only, set(dag_downstream_closure([stages[0]])), change_type)

    def test_quality_nodes_appear_in_quality_related_impacts(self) -> None:
        from remix_reference_video.change_service import _IMPACTS

        self.assertIn("build-narrative-coherence", _IMPACTS["copy"]["stale_stages"])
        self.assertNotIn("validate-visual-layout", _IMPACTS["copy"]["stale_stages"])
        self.assertIn("validate-visual-layout", _IMPACTS["material"]["stale_stages"])
        self.assertIn("build-narrative-coherence", _IMPACTS["material"]["stale_stages"])
        self.assertIn("narrative_coherence_report.json", _IMPACTS["copy"]["artifacts_to_regenerate"])
        self.assertIn("visual_layout_report.json", _IMPACTS["material"]["artifacts_to_regenerate"])
        self.assertNotIn("build-narrative-coherence", _IMPACTS["voice"]["stale_stages"])
        self.assertNotIn("validate-visual-layout", _IMPACTS["rerecord"]["stale_stages"])

    def test_creative_preview_uses_the_selected_dag_closure(self) -> None:
        atomic_write_json(self.root / "g_b_frozen_input_snapshot.json", {"creative_contract_version": "creative_contract_v1"})
        request = {"change_type":"copy","scope_ids":["line01"],"payload":{"line_ids":["line01"],"text_by_id":{"line01":"改写"},"edit_intent":"rewrite"},"reason":"改写"}
        preview = self.analyzer.preview(session_id=self.session["session_id"], gate_id="gate3_material_selection", request=request)
        self.assertIn("generate-script-candidates", preview["stale_stages"])
        self.assertIn("build-final-content-diagnostic", preview["stale_stages"])

    def test_gate2_changes_invalidate_material_evidence_contracts(self) -> None:
        from remix_reference_video.change_service import _IMPACTS

        for change_type in ("claim_scope", "structural"):
            with self.subTest(change_type=change_type):
                impact = _IMPACTS[change_type]
                self.assertIn("build-material-evidence-requirements", impact["stale_stages"])
                self.assertIn("material_evidence_requirements.json", impact["artifacts_to_regenerate"])
                self.assertIn("material_evidence_annotations.json", impact["artifacts_to_regenerate"])

    def test_script_candidate_select_requires_passed_candidate_and_stales_gate4(self) -> None:
        session = self._switch_to_gate4_pre()
        candidates = {
            "candidates": [
                {"script_candidate_id": "script-1", "status": "candidate", "lines": [{"line_id": "line01", "text": "新脚本"}]},
                {"script_candidate_id": "script-2", "status": "candidate", "lines": [{"line_id": "line01", "text": "候选脚本"}]},
            ]
        }
        validation = {"candidates": [{"script_candidate_id": "script-1", "status": "passed"}, {"script_candidate_id": "script-2", "status": "blocked"}]}
        atomic_write_json(self.root / "script_candidates.json", candidates)
        atomic_write_json(self.root / "script_candidate_validation_report.json", validation)
        digest = hashlib.sha256((self.root / "script_candidates.json").read_bytes()).hexdigest()
        request = {"change_type": "script_candidate_select", "scope_ids": ["script-1"], "payload": {"script_candidate_id": "script-1", "script_candidates_sha256": digest}, "reason": "选择更连贯的脚本候选"}
        preview = self.analyzer.preview(session_id=session["session_id"], gate_id="gate4_pre_generation", request=request)
        self.assertEqual(preview["earliest_affected_gate"], "gate4_pre_generation")
        self.assertIn("production_script_candidate.json", preview["artifacts_to_regenerate"])
        self.assertIn("voice_preflight.json", preview["artifacts_to_regenerate"])
        self.assertIn("gate4_pre_generation", preview["stale_gates"])
        self.assertIn("build-production-script", preview["stale_stages"])
        self.assertNotIn("validate-visual-layout", preview["stale_stages"])
        bad = dict(request, payload={**request["payload"], "script_candidate_id": "script-2"}, scope_ids=["script-2"])
        with self.assertRaisesRegex(ChangeConflict, "passed"):
            self.analyzer.preview(session_id=session["session_id"], gate_id="gate4_pre_generation", request=bad)

    def test_script_candidate_select_materializes_candidate_and_handoff(self) -> None:
        candidates = {"candidates": [{"script_candidate_id": "script-1", "status": "candidate", "lines": [{"line_id": "line01", "text": "新脚本"}]}]}
        validation = {"candidates": [{"script_candidate_id": "script-1", "status": "passed"}]}
        atomic_write_json(self.root / "script_candidates.json", candidates)
        atomic_write_json(self.root / "script_candidate_validation_report.json", validation)
        override = {
            "change_type": "script_candidate_select",
            "change_request_id": "candidate-change-1",
            "request": {"payload": {"script_candidate_id": "script-1"}},
        }
        WorkbenchOrchestrator._materialize_override(self.root, override)
        selected = read_json_object(self.root / "production_script_candidate.json")
        self.assertEqual(selected["selected_script_candidate_id"], "script-1")
        handoff = read_json_object(self.root / "stage_inputs/select-script-candidate.json")
        self.assertEqual(handoff["payload"], {"script_candidate_id": "script-1"})


if __name__ == "__main__": unittest.main()
