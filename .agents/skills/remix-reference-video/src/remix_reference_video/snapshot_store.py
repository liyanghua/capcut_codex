"""Immutable versioned storage for Track-B measurement snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .baseline_policy import BaselinePolicy
from .measurement import Phase6Snapshot
from .process_assessment import ProcessAssessmentBuilder
from .snapshot_schema_validator import SnapshotSchemaValidator
from .storage import read_json_object, read_jsonl_records


class SnapshotStoreError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


class SnapshotStore:
    def __init__(self, task_dir: Path) -> None:
        self.root = Path(task_dir).resolve(strict=True)
        if not self.root.is_dir():
            raise SnapshotStoreError("task directory must be a directory")
        self.validator = SnapshotSchemaValidator()

    def build(self, *, rubric_path: Path, policy_path: Path) -> dict[str, Any]:
        state = read_json_object(self.root / "pipeline_state.json")
        run_id = state.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise SnapshotStoreError("pipeline_state.run_id is required")
        rubric = read_json_object(Path(rubric_path).resolve(strict=True))
        policy = BaselinePolicy.from_mapping(read_json_object(Path(policy_path).resolve(strict=True)))
        events = read_jsonl_records(self.root / "pipeline_events.jsonl")
        metrics = read_jsonl_records(self.root / "stage_metrics.jsonl")
        process = ProcessAssessmentBuilder().build(state=state, events=events, metrics=metrics, run_id=run_id, execution_mode=str(state.get("execution_mode", "unknown")))
        frozen = self.root / "g_b_frozen_input_snapshot.json"
        frozen_hash = _sha256(frozen) if frozen.is_file() else ""
        role = "hot" if self.root.name == "hot" else "cold"
        if role == "hot" and frozen_hash != policy.value.get("frozen_input_sha256"):
            cold_snapshot = self.root.parent / "cold" / "g_b_frozen_input_snapshot.json"
            if cold_snapshot.is_file() and _canonical_file_hash(cold_snapshot) == _canonical_file_hash(frozen):
                frozen_hash = str(policy.value["frozen_input_sha256"])
        baseline = policy.compare(frozen_snapshot_sha256=frozen_hash, run_role=role)
        baseline["run_role"] = role
        stages = rubric.get("framework_stages")
        if not isinstance(stages, list):
            raise SnapshotStoreError("rubric input framework_stages is required")
        input_hashes = {name: _sha256(path) for name, path in (("pipeline_state.json", self.root / "pipeline_state.json"), ("pipeline_events.jsonl", self.root / "pipeline_events.jsonl"), ("stage_metrics.jsonl", self.root / "stage_metrics.jsonl"), ("g_b_frozen_input_snapshot.json", frozen)) if path.is_file()}
        phase = Phase6Snapshot().build(run_id=run_id, state_revision=state.get("state_revision"), framework_stages=stages, process_assessment=process, baseline_result=baseline, input_hashes=input_hashes, lifecycle_status="incomplete")
        snapshot_id = str(phase["snapshot_id"])
        directory = self.root / "measurements" / snapshot_id
        if directory.exists():
            existing = read_json_object(directory / "phase6_score_snapshot.json")
            if _canonical_hash(existing) == _canonical_hash(phase):
                return {"status": "idempotent", "snapshot_id": snapshot_id, "path": str(directory)}
            phase["supersedes_snapshot_id"] = snapshot_id
            phase["snapshot_id"] = f"{snapshot_id}-{_canonical_hash(phase)[:8]}"
            directory = self.root / "measurements" / str(phase["snapshot_id"])
        self.validator.assert_valid(phase, "phase6-score-snapshot.schema.json")
        self.validator.assert_valid(process, "process-assessment.schema.json")
        staging = Path(tempfile.mkdtemp(prefix="snapshot-", dir=str(self.root / "measurements" if (self.root / "measurements").is_dir() else self.root)))
        try:
            (staging / "phase6_score_snapshot.json").write_text(json.dumps(phase, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (staging / "process_assessment.json").write_text(json.dumps(process, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (staging / "phase6_score_snapshot.json").open("rb").flush()
            directory.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, directory)
            latest = {"snapshot_id": phase["snapshot_id"], "phase6_score_snapshot": {"path": str(directory / "phase6_score_snapshot.json"), "sha256": _sha256(directory / "phase6_score_snapshot.json")}, "process_assessment": {"path": str(directory / "process_assessment.json"), "sha256": _sha256(directory / "process_assessment.json")}}
            latest_tmp = directory.parent / ".latest.tmp"
            latest_tmp.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(latest_tmp, directory.parent / "latest.json")
        finally:
            if staging.exists():
                for child in staging.iterdir(): child.unlink()
                staging.rmdir()
        return {"status": "created", "snapshot_id": phase["snapshot_id"], "path": str(directory), "phase6_score_snapshot": str(directory / "phase6_score_snapshot.json"), "process_assessment": str(directory / "process_assessment.json")}


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _canonical_file_hash(path: Path) -> str:
    value = read_json_object(path)
    if isinstance(value, dict):
        value = {key: item for key, item in value.items() if key != "pair_role"}
    return _canonical_hash(value)
