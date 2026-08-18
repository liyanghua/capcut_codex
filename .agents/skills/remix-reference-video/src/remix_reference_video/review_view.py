"""Deterministic business-facing Gate review views and static fallback files."""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .snapshot_schema_validator import SnapshotSchemaValidator
from .storage import StorageError, atomic_write_json, read_json_object


_GATE_META = {
    "gate1": ("参考片拆解", "镜头切分是否可接受？", 3, "gate1-change-v1"),
    "gate2": ("复刻方案", "内容基线与变更包是否批准？", 5, "gate2-change-v1"),
    "gate3_material_selection": ("素材选配", "每段配的素材画面是否可用？", 5, "gate3-material-change-v1"),
    "gate3_evidence_closure": ("证据闭环", "每句口播是否都有对应画面证据？", 3, "gate3-evidence-change-v1"),
    "gate4_pre_generation": ("文案与声音", "文案、音色和语速是否批准？", 3, "gate4-pre-change-v1"),
    "gate4_post_generation": ("配音听审", "逐句配音是否可用？", 5, "gate4-post-change-v1"),
    "gate5": ("成片终审", "最终预览是否通过？", 5, "gate5-change-v1"),
}

_GATE_EVIDENCE = {
    "gate1": ("recipe.json", "review_contact_sheet.jpg"),
    "gate2": ("content_baseline.json", "mutation_plan.json", "shot_blueprint.json"),
    "gate3_material_selection": ("material_selection_candidate.json", "matches.json", "gate3_review_contact_sheet.jpg"),
    "gate3_evidence_closure": ("script_evidence_matrix.json",),
    "gate4_pre_generation": ("production_script_candidate.json", "voice_preflight.json"),
    "gate4_post_generation": ("voice/voice_manifest.json", "reconstruction_timeline.json", "captions.srt"),
    "gate5": ("remix.mp4", "captions.srt", "final_validation_report.json", "render_report.json", "jianying_import_manifest.json"),
}


class ReviewViewError(StorageError):
    pass


class ReviewViewBuilder:
    def __init__(self, task_root: Path) -> None:
        self.root = Path(task_root).resolve(strict=True)
        if not self.root.is_dir():
            raise ReviewViewError("task root must be a directory")
        self.validator = SnapshotSchemaValidator()

    def build(self, gate_id: str, *, projected_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if gate_id not in _GATE_META:
            raise ReviewViewError(f"unsupported Gate: {gate_id}")
        state = dict(projected_state) if projected_state is not None else read_json_object(self.root / "pipeline_state.json")
        package_path = self._file(self.root / "gate_review_packages" / f"{gate_id}.json")
        package = read_json_object(package_path)
        if package.get("gate_id") != gate_id or package.get("run_id") != state.get("run_id"):
            raise ReviewViewError("review package identity does not match task")
        if package.get("state_revision") != state.get("state_revision"):
            raise ReviewViewError("review package revision is stale")
        package_hash = self._sha256(package_path)
        trusted_service_time = package.get("created_at")
        if not isinstance(trusted_service_time, str) or not trusted_service_time:
            raise ReviewViewError("review package trusted service time is missing")
        business_name, question, minutes, form_schema = _GATE_META[gate_id]
        evidence = self._evidence(gate_id, package_path)
        risks = self._risks(state, package)
        last_diff = self._last_approval_diff(state, gate_id, package.get("input_hashes"))
        gate_status = state.get("gate_status", {}).get(gate_id) if isinstance(state.get("gate_status"), Mapping) else None
        lifecycle = "stale" if gate_status == "stale" else "ready"
        impacts = self._business_impacts(gate_id, package, evidence)
        snapshot_seed = f"{state['run_id']}:{gate_id}:{state['state_revision']}:{package_hash}"
        snapshot_id = "review-" + hashlib.sha256(snapshot_seed.encode()).hexdigest()[:24]
        idempotency_key = "review-view-" + hashlib.sha256(snapshot_seed.encode()).hexdigest()
        source_versions = {"contract_version": "2.0.0-alpha.1", "skill_version": "2.0.0-alpha.1"}
        view: dict[str, Any] = {
            "artifact_type": "gate_review_view",
            "schema_id": "urn:capcut:remix-reference-video:artifact:gate-review-view",
            "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1", "skill_version": "2.0.0-alpha.1",
            "snapshot_id": snapshot_id, "run_id": state["run_id"], "gate_id": gate_id,
            "state_revision": state["state_revision"], "bound_package_sha256": package_hash,
            "lifecycle_status": lifecycle,
            "trusted_service_time": trusted_service_time,
            "policy_id": "review-workbench-p0b", "policy_version": "1.0.0",
            "source_versions": source_versions, "idempotency_key": idempotency_key,
            "review_meta": {"business_name": business_name, "decision_question": question, "expected_minutes": minutes},
            "business_summary": {"current_step": f"当前待确认：{business_name}", "business_impacts": impacts, "recommendation": self._recommendation(evidence, risks)},
            "available_actions": ["approve", "reject", "request_changes"],
            "evidence": evidence, "risks": risks,
            "impact_context": {
                "change_form_schema": form_schema,
                "last_approval_diff": last_diff,
                "decision_scope_ids": self._decision_scope_ids(gate_id),
                "change_options": self._change_options(gate_id),
            },
            "technical_appendix": {"input_hashes": dict(package.get("input_hashes", {})), "package_path": f"gate_review_packages/{gate_id}.json"},
            "input_hashes": dict(package.get("input_hashes", {})), "supersedes_snapshot_id": None,
        }
        self.validator.assert_valid(view, "gate-review-view.schema.json")
        return view

    def write_snapshot(self, gate_id: str, *, projected_state: Mapping[str, Any] | None = None) -> dict[str, str]:
        view = self.build(gate_id, projected_state=projected_state)
        directory = self.root / "gate_review_packages" / f"{gate_id}.review"
        directory.mkdir(parents=True, exist_ok=True)
        view_path = directory / "gate_review_view.json"
        html_path = directory / "review.html"
        markdown_path = directory / "snapshot.md"
        sheet_path = directory / "gate_review_sheet.json"
        atomic_write_json(view_path, view)
        html_path.write_text(self._html(view), encoding="utf-8")
        markdown_path.write_text(self._markdown(view), encoding="utf-8")
        sheet = {
            "artifact_type": "gate_review_sheet", "schema_id": "urn:capcut:remix-reference-video:artifact:gate-review-sheet",
            "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1", "skill_version": "2.0.0-alpha.1",
            "snapshot_id": "sheet-" + str(view["snapshot_id"]),
            "run_id": view["run_id"], "gate_id": gate_id, "state_revision": view["state_revision"],
            "bound_package_sha256": view["bound_package_sha256"], "lifecycle_status": "derived_review_only",
            "input_hashes": dict(view["input_hashes"]), "source_versions": dict(view["source_versions"]),
            "policy_id": view["policy_id"], "policy_version": view["policy_version"],
            "trusted_service_time": view["trusted_service_time"], "idempotency_key": "sheet-" + str(view["idempotency_key"]),
            "supersedes_snapshot_id": None,
            "view_path": view_path.relative_to(self.root).as_posix(), "html_path": html_path.relative_to(self.root).as_posix(), "markdown_path": markdown_path.relative_to(self.root).as_posix(),
        }
        self.validator.assert_valid(sheet, "gate-review-sheet.schema.json")
        atomic_write_json(sheet_path, sheet)
        return {"view_path": str(view_path), "sheet_path": str(sheet_path), "html_path": str(html_path), "markdown_path": str(markdown_path)}

    def _evidence(self, gate_id: str, package_path: Path) -> list[dict[str, Any]]:
        rows = [{"evidence_id": "review_package", "kind": "json", "status": "available", "path": package_path.relative_to(self.root).as_posix()}]
        for relative in _GATE_EVIDENCE[gate_id]:
            path = self.root / relative
            kind = path.suffix.lower().lstrip(".") or "file"
            rows.append({"evidence_id": relative.replace("/", "_"), "kind": kind, "status": "available" if path.is_file() and not path.is_symlink() else "missing", "path": relative})
        return rows

    @staticmethod
    def _risks(state: Mapping[str, Any], package: Mapping[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        blockers = state.get("blockers") if isinstance(state.get("blockers"), list) else []
        for blocker in blockers:
            if isinstance(blocker, Mapping):
                rows.append({"severity": "error" if blocker.get("requires_user", True) else "warning", "message": str(blocker.get("detail") or blocker.get("category") or "未说明阻塞"), "blocking": bool(blocker.get("requires_user", True))})
        raw_risks = package.get("known_nonblocking_risks")
        if isinstance(raw_risks, list):
            for risk in raw_risks[:3]:
                rows.append({"severity": "info", "message": str(risk), "blocking": False})
        return rows

    @staticmethod
    def _last_approval_diff(state: Mapping[str, Any], gate_id: str, current_hashes: object) -> dict[str, list[str]]:
        current = dict(current_hashes) if isinstance(current_hashes, Mapping) else {}
        previous: Mapping[str, object] = {}
        decisions = state.get("decisions") if isinstance(state.get("decisions"), list) else []
        for decision in decisions:
            if isinstance(decision, Mapping) and decision.get("gate_id") == gate_id and decision.get("decision") == "approved" and isinstance(decision.get("input_hashes"), Mapping):
                previous = decision["input_hashes"]
        changed = sorted(key for key in set(current) | set(previous) if current.get(key) != previous.get(key))
        unchanged = sorted(key for key in set(current) & set(previous) if current.get(key) == previous.get(key))
        return {"changed": changed, "unchanged": unchanged}

    @staticmethod
    def _business_impacts(gate_id: str, package: Mapping[str, Any], evidence: list[dict[str, Any]]) -> list[str]:
        missing = sum(1 for item in evidence if item["status"] == "missing")
        base = {
            "gate1": "批准后将以当前镜头顺序规划复刻内容。",
            "gate2": "批准后内容基线与受控变更包一起生效。",
            "gate3_material_selection": "批准后当前素材来源和宽范围进入生产准备。",
            "gate3_evidence_closure": "批准后仅使用已有画面证据编译生产文案。",
            "gate4_pre_generation": "批准后才允许按当前文案和声音设置生成配音。",
            "gate4_post_generation": "批准后才允许进入代理检查和正式渲染。",
            "gate5": "批准只确认当前成片，不自动解除普通生产锁。",
        }[gate_id]
        rows = [base]
        if missing:
            rows.append(f"有 {missing} 项辅助证据缺失，需要在决定前确认是否阻塞。")
        if isinstance(package.get("selections"), list):
            rows.append(f"本轮包含 {len(package['selections'])} 个素材选择。")
        return rows[:3]

    @staticmethod
    def _recommendation(evidence: list[dict[str, Any]], risks: list[dict[str, Any]]) -> dict[str, str]:
        if any(item["blocking"] for item in risks):
            return {"action": "reject", "reason": "当前仍有需要用户处理的阻塞项。"}
        missing = sum(1 for item in evidence if item["status"] == "missing")
        if missing:
            return {"action": "request_changes", "reason": "辅助证据不完整，建议先补齐或明确豁免。"}
        return {"action": "approve", "reason": "当前机器包和关键证据均已登记。"}

    def _file(self, path: Path) -> Path:
        if path.is_symlink():
            raise ReviewViewError("review path must not be a symlink")
        resolved = path.resolve(strict=True)
        if self.root not in resolved.parents or not resolved.is_file():
            raise ReviewViewError("review path escapes task root")
        return resolved

    def _decision_scope_ids(self, gate_id: str) -> list[str]:
        options = self._change_options(gate_id)
        fragments = options.get("fragments")
        if gate_id == "gate3_material_selection" and isinstance(fragments, list):
            values = [str(row["fragment_id"]) for row in fragments if isinstance(row, Mapping) and isinstance(row.get("fragment_id"), str)]
            if values:
                return values
        return [gate_id]

    def _change_options(self, gate_id: str) -> dict[str, Any]:
        options: dict[str, Any] = {
            "allowed_change_types": {
                "gate1": ["structural"],
                "gate2": ["claim_scope", "structural"],
                "gate3_material_selection": ["material", "range", "structural"],
                "gate3_evidence_closure": ["copy", "claim_scope", "structural"],
                "gate4_pre_generation": ["copy", "voice", "structural"],
                "gate4_post_generation": ["rerecord", "copy", "voice"],
                "gate5": ["boundary", "material", "range", "rerecord", "copy", "voice", "structural"],
            }[gate_id],
            "overlay_options": [
                {"value":"retain_source_text","label":"保留源文字"}, {"value":"crop","label":"裁切"},
                {"value":"cover","label":"遮盖"}, {"value":"replace","label":"替换"},
                {"value":"no_action","label":"无需处理"},
            ],
        }
        baseline = self._optional_json("content_baseline.json")
        if baseline:
            options["claims"] = [
                {"claim_id":row["claim_id"],"label":row.get("text", row["claim_id"])}
                for row in baseline.get("claims", []) if isinstance(row, Mapping) and isinstance(row.get("claim_id"), str)
            ]
            options["structure_fragments"] = [
                {"fragment_id":row["fragment_id"],"label":row.get("narration", row["fragment_id"])}
                for row in baseline.get("fragments", []) if isinstance(row, Mapping) and isinstance(row.get("fragment_id"), str)
            ]
        candidate = self._optional_json("production_script_candidate.json")
        if candidate:
            options["lines"] = [
                {"line_id":row["line_id"],"fragment_id":row.get("fragment_id"),"text":row.get("text", "")}
                for row in candidate.get("lines", []) if isinstance(row, Mapping) and isinstance(row.get("line_id"), str)
            ]
        approved = self._optional_json("approved_production_script.json")
        if approved:
            voice_policy = approved.get("allowed_tts_settings")
            current_voice = approved.get("tts_settings")
            options["voice"] = {
                "current": dict(current_voice) if isinstance(current_voice, Mapping) else {},
                "allowed": dict(voice_policy) if isinstance(voice_policy, Mapping) else {},
            }
            options["rerecord"] = [
                {
                    "fragment_id":row["fragment_id"],
                    "line_id":row.get("line_id"),
                    "text":row.get("text", ""),
                    "approved_text_sha256":hashlib.sha256(str(row.get("text", "")).encode("utf-8")).hexdigest(),
                }
                for row in approved.get("lines", []) if isinstance(row, Mapping) and isinstance(row.get("fragment_id"), str) and isinstance(row.get("text"), str)
            ]
        if gate_id in {"gate3_material_selection", "gate5"}:
            matches = self._optional_json("matches.json")
            plan = self._optional_json("fragment_plan.json")
            ranges = {
                str(row["fragment_id"]): dict(row["approved_broad_range"])
                for row in (plan or {}).get("fragments", [])
                if isinstance(row, Mapping) and isinstance(row.get("fragment_id"), str) and isinstance(row.get("approved_broad_range"), Mapping)
            }
            fragments = []
            for row in (matches or {}).get("fragments", []):
                if not isinstance(row, Mapping) or not isinstance(row.get("fragment_id"), str):
                    continue
                fragment_id = str(row["fragment_id"])
                candidates = []
                for item in row.get("candidates", []):
                    if not isinstance(item, Mapping):
                        continue
                    candidate_id = item.get("candidate_id", item.get("asset_id"))
                    source_hash = item.get("source_sha256", item.get("sha256"))
                    if not isinstance(candidate_id, str) or not isinstance(source_hash, str):
                        continue
                    candidates.append({
                        "candidate_id":candidate_id,
                        "source_sha256":source_hash,
                        "label":str(item.get("source_id") or item.get("source_path") or candidate_id),
                    })
                broad = ranges.get(fragment_id)
                if broad is None and candidates and isinstance(row.get("candidates"), list):
                    first = row["candidates"][0]
                    raw_ranges = first.get("broad_ranges") if isinstance(first, Mapping) else None
                    if isinstance(raw_ranges, list) and raw_ranges and isinstance(raw_ranges[0], Mapping):
                        broad = dict(raw_ranges[0])
                fragments.append({"fragment_id":fragment_id,"candidates":candidates,"range":broad})
            options["fragments"] = fragments
        if gate_id == "gate5":
            report = self._optional_json("proxy_boundary_report.json")
            options["boundaries"] = [
                {"boundary_id":str(row.get("boundary_id") or f"b{index:02d}"),"boundary_seconds":row.get("boundary_seconds"),"status":row.get("status")}
                for index, row in enumerate((report or {}).get("boundary_frames", []), 1) if isinstance(row, Mapping)
            ]
        return options

    def _optional_json(self, relative: str) -> dict[str, Any] | None:
        state = read_json_object(self.root / "pipeline_state.json")
        artifacts = state.get("artifacts", {})
        if relative == "approved_production_script.json" and isinstance(artifacts, Mapping):
            artifact = artifacts.get("approved_production_script")
            if isinstance(artifact, Mapping) and isinstance(artifact.get("path"), str):
                relative = str(artifact["path"])
        elif relative == "fragment_plan.json" and isinstance(artifacts, Mapping):
            versions = [
                str(item["path"])
                for item in artifacts.values()
                if isinstance(item, Mapping)
                and isinstance(item.get("path"), str)
                and str(item["path"]).startswith("versions/fragment_plan/")
                and str(item["path"]).endswith("/fragment_plan.json")
            ]
            if versions:
                relative = max(versions)
        path = self.root / relative
        if path.is_symlink() or not path.is_file():
            return None
        return read_json_object(path)

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    @staticmethod
    def _markdown(view: Mapping[str, Any]) -> str:
        meta = view["review_meta"]; summary = view["business_summary"]
        impacts = "\n".join(f"- {item}" for item in summary["business_impacts"])
        risks = "\n".join(f"- {item['message']}" for item in view["risks"]) or "- 无"
        return f"# {meta['business_name']}\n\n## 现在到哪\n\n{summary['current_step']}\n\n## 业务影响\n\n{impacts}\n\n## 只需确认\n\n{meta['decision_question']}\n\n## 建议\n\n{summary['recommendation']['reason']}\n\n## 未处理风险\n\n{risks}\n\n## 决策操作\n\n通过 / 驳回 / 要求修改\n"

    @staticmethod
    def _html(view: Mapping[str, Any]) -> str:
        meta = view["review_meta"]; summary = view["business_summary"]
        impacts = "".join(f"<li>{html.escape(str(item))}</li>" for item in summary["business_impacts"])
        return "<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><title>" + html.escape(str(meta["business_name"])) + "</title><body><main><h1>" + html.escape(str(meta["business_name"])) + "</h1><h2>现在到哪</h2><p>" + html.escape(str(summary["current_step"])) + "</p><h2>业务影响</h2><ul>" + impacts + "</ul><h2>只需确认</h2><p>" + html.escape(str(meta["decision_question"])) + "</p><h2>建议</h2><p>" + html.escape(str(summary["recommendation"]["reason"])) + "</p><div><button>通过</button><button>要求修改</button><button>驳回</button></div></main></body></html>\n"
