"""Command-line entry point for the experimental Fast Path v0."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .asset_index import AssetIndexer, AssetIndexPrerequisiteError
from .approvals import ApprovalError, ApprovalService
from .adapters.reference_split import ReferenceSplitAdapter
from .artifact_validator import ArtifactValidator
from .stage_input_validator import StageInputValidator
from .contracts import (
    PRODUCTION_EXECUTION_MODE,
    ExecutionPlan,
    PipelineState,
    PlanValidationError,
)
from .ga_evidence import audit_ga, prepare_review, record_decision
from .gb_frozen_case import (
    clone_declared_cold_cache,
    prepare_frozen_pair,
    reuse_existing_hot_cache,
    validate_frozen_input,
    write_pair_measurement,
)
from .measurement import MeasurementError
from .production_runtime import ProductionRuntimeConfig, build_real_registry
from .runner import FastPathRunner, ProductionRunner
from .storage import StorageError, read_json_object, read_jsonl_records
from .storage import TaskStorage


EXIT_OK = 0
EXIT_INVALID = 2
EXIT_AWAITING_USER = 3
EXIT_BLOCKED = 4
EXIT_FAILED = 5

_ALLOWED_GATE_STATUSES = frozenset(
    {"not_started", "running", "awaiting_user", "approved", "blocked", "stale", "failed"}
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="remixctl")
    commands = parser.add_subparsers(dest="command", required=True)

    fast = commands.add_parser("fast")
    fast.add_argument("--workspace-root", type=Path, required=True)
    fast.add_argument("--plan", type=Path, required=True)
    fast.add_argument("--json", action="store_true")

    initialize = commands.add_parser("init")
    initialize.add_argument("--workspace-root", type=Path, required=True)
    initialize.add_argument("--task-dir", type=Path, required=True)
    initialize.add_argument("--reference", type=Path, required=True)
    initialize.add_argument("--json", action="store_true")

    def add_runtime_config_option(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--runtime-config",
            type=Path,
            help="Validated production_runtime_config.json for the real Native Registry",
        )

    for command in ("run", "stage", "production-run", "production-stage"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--task-dir", type=Path, required=True)
        subparser.add_argument("--reference", type=Path)
        if command in {"stage", "production-stage"}:
            subparser.add_argument("--stage", required=True)
        add_runtime_config_option(subparser)
        subparser.add_argument("--json", action="store_true")

    resume = commands.add_parser("resume")
    resume.add_argument("--workspace-root", type=Path)
    resume.add_argument("--plan", type=Path)
    resume.add_argument("--task-dir", type=Path)
    resume.add_argument("--reference", type=Path)
    add_runtime_config_option(resume)
    resume.add_argument("--json", action="store_true")

    production_resume = commands.add_parser("production-resume")
    production_resume.add_argument("--task-dir", type=Path, required=True)
    production_resume.add_argument("--reference", type=Path)
    add_runtime_config_option(production_resume)
    production_resume.add_argument("--json", action="store_true")

    for command in ("status", "audit", "production-status", "production-audit"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--task-dir", type=Path, required=True)
        subparser.add_argument("--json", action="store_true")

    prepare = commands.add_parser("ga-prepare-review")
    prepare.add_argument("--task-dir", type=Path, required=True)
    prepare.add_argument("--gate", required=True)
    prepare.add_argument("--artifact", action="append", required=True)
    prepare.add_argument("--json", action="store_true")

    decide = commands.add_parser("ga-record-decision")
    decide.add_argument("--task-dir", type=Path, required=True)
    decide.add_argument("--gate", required=True)
    decide.add_argument("--review-package", required=True)
    decide.add_argument("--decision-file", required=True)
    decide.add_argument("--actor", required=True)
    decide.add_argument("--json", action="store_true")

    ga_audit = commands.add_parser("ga-audit")
    ga_audit.add_argument("--task-dir", type=Path, required=True)
    ga_audit.add_argument("--json", action="store_true")

    approve = commands.add_parser("approve-gate")
    approve.add_argument("--task-dir", type=Path, required=True)
    approve.add_argument("--gate", required=True)
    approve.add_argument("--review-package-hash", required=True)
    approve.add_argument("--decision-file", type=Path, required=True)
    approve.add_argument("--actor", required=True)
    approve.add_argument("--json", action="store_true")

    index = commands.add_parser("index-assets")
    index.add_argument("--assets-root", type=Path, required=True)
    index.add_argument("--database", type=Path, required=True)
    index.add_argument("--json", action="store_true")

    pair = commands.add_parser(
        "gb-pair",
        help="run an isolated frozen-input G-B cold/hot pair; ordinary Track B stays locked",
    )
    pair.add_argument("--frozen-root", type=Path, required=True)
    pair.add_argument("--asset-root", type=Path, required=True)
    pair.add_argument("--cold-task-dir", type=Path, required=True)
    pair.add_argument("--hot-task-dir", type=Path, required=True)
    pair.add_argument("--pair-root", type=Path, required=True)
    pair.add_argument("--doubao-client", type=Path)
    pair.add_argument("--python-executable", default=sys.executable)
    pair.add_argument("--decision-dir", type=Path)
    pair.add_argument("--actor", default="gb-owner")
    pair.add_argument(
        "--resume-existing",
        action="store_true",
        help="resume the declared isolated pair without recreating task roots",
    )
    pair.add_argument("--json", action="store_true")
    return parser


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _task_root(path: Path) -> Path:
    root = path.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"task directory is not a directory: {root}")
    return root


def _current_gate(state: dict[str, Any]) -> tuple[str | None, str | None]:
    gates = state.get("gate_status", {})
    if not isinstance(gates, dict):
        return None, None
    for target in ("awaiting_user", "blocked", "stale", "failed"):
        for gate_id, status in gates.items():
            if status == target:
                return str(gate_id), target
    return None, None


def status_snapshot(task_dir: Path) -> dict[str, Any]:
    """Read a minimal status projection without creating or changing task files."""

    root = _task_root(task_dir)
    state = read_json_object(root / "pipeline_state.json")
    gate_id, gate_status = _current_gate(state)
    fast_path = state.get("fast_path", {})
    fast_path_status = (
        fast_path.get("run_status") if isinstance(fast_path, dict) else None
    )
    return {
        "run_id": state.get("run_id"),
        "execution_mode": state.get("execution_mode"),
        "run_status": fast_path_status or state.get("run_status"),
        "current_stage": state.get("current_stage"),
        "state_revision": state.get("state_revision"),
        "gate_id": gate_id,
        "gate_status": gate_status,
    }


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def audit_task(task_dir: Path) -> dict[str, Any]:
    """Validate readable Fast Path facts without repairing or writing anything."""

    root = _task_root(task_dir)
    state = read_json_object(root / "pipeline_state.json")
    if state.get("execution_mode") == PRODUCTION_EXECUTION_MODE:
        return _audit_production_task(root, state)
    errors: list[str] = []
    warnings: list[str] = []
    mode = state.get("execution_mode")
    if not isinstance(mode, str) or mode not in {
        "fast-path-v0",
        "manual-contract-only",
    }:
        errors.append("unsupported execution_mode")
    if mode == "manual-contract-only":
        warnings.append("protected manual-contract-only task; audit is read-only")
    if not isinstance(state.get("run_id"), str) or not state["run_id"]:
        errors.append("run_id is missing")
    gates = state.get("gate_status", {})
    if not isinstance(gates, dict):
        errors.append("gate_status must be an object")
    else:
        for gate_id, gate_status in gates.items():
            if (
                not isinstance(gate_status, str)
                or gate_status not in _ALLOWED_GATE_STATUSES
            ):
                errors.append(f"{gate_id} has invalid status {gate_status!r}")

    events = read_jsonl_records(root / "pipeline_events.jsonl")
    sequences = [event.get("sequence") for event in events]
    if sequences and sequences != list(range(1, len(sequences) + 1)):
        errors.append("event sequence is not contiguous")
    revision = state.get("state_revision")
    if mode == "fast-path-v0" and (
        isinstance(revision, bool) or not isinstance(revision, int) or revision < 0
    ):
        errors.append("state_revision must be a nonnegative integer")
    if isinstance(revision, int) and not isinstance(revision, bool):
        raw_event_revisions = [event.get("state_revision") for event in events]
        if any(
            isinstance(event_revision, bool)
            or not isinstance(event_revision, int)
            or event_revision < 0
            for event_revision in raw_event_revisions
        ):
            errors.append("event state_revision values must be nonnegative integers")
        event_revisions = [
            event_revision
            for event_revision in raw_event_revisions
            if isinstance(event_revision, int) and not isinstance(event_revision, bool)
        ]
        if any(
            current < previous
            for previous, current in zip(event_revisions, event_revisions[1:])
        ):
            errors.append("event state_revision is not monotonic")
        last_event_revision = max(event_revisions, default=0)
        if last_event_revision > revision:
            errors.append("event log is ahead of pipeline state")
        elif last_event_revision < revision:
            warnings.append("event log is behind pipeline state")

    fast_path = state.get("fast_path", {})
    gate_inputs = fast_path.get("gate_inputs") if isinstance(fast_path, dict) else None
    decisions = state.get("decisions", [])
    if mode == "fast-path-v0" and isinstance(gates, dict):
        for gate_id, gate_status in gates.items():
            if gate_status != "approved":
                continue
            expected = gate_inputs.get(gate_id) if isinstance(gate_inputs, dict) else None
            expected_hashes = expected.get("output_hashes") if isinstance(expected, dict) else None
            valid_decision = False
            if isinstance(expected_hashes, dict) and expected_hashes and isinstance(decisions, list):
                for decision in reversed(decisions):
                    if not isinstance(decision, dict):
                        continue
                    if (
                        decision.get("gate_id") != gate_id
                        and decision.get("substate_id") != gate_id
                    ):
                        continue
                    if decision.get("decision") != "approved":
                        continue
                    decision_status = decision.get("status")
                    if not isinstance(decision_status, (str, type(None))):
                        continue
                    if decision_status in {"revoked", "stale", "superseded"}:
                        continue
                    input_hashes = decision.get("input_hashes")
                    if isinstance(input_hashes, dict) and all(
                        input_hashes.get(path) == digest
                        for path, digest in expected_hashes.items()
                    ):
                        valid_decision = True
                        break
            if not valid_decision:
                errors.append(f"{gate_id} approval is not hash-bound")

    raw_cache = fast_path.get("stage_cache") if isinstance(fast_path, dict) else None
    cache = raw_cache if isinstance(raw_cache, dict) else {}
    if raw_cache is not None and not isinstance(raw_cache, dict):
        errors.append("stage_cache must be an object")
    for stage_id, record in cache.items():
        output_hashes = record.get("output_hashes") if isinstance(record, dict) else None
        if not isinstance(output_hashes, dict):
            errors.append(f"{stage_id} cache has no output_hashes")
            continue
        for relative, expected_hash in output_hashes.items():
            declared = Path(relative)
            resolved = (root / declared).resolve(strict=False)
            if declared.is_absolute() or not _inside(resolved, root):
                errors.append(f"{stage_id} cache output escapes task root")
            elif not resolved.is_file():
                errors.append(f"{stage_id} cache output is missing: {relative}")
            elif not isinstance(expected_hash, str) or _sha256(resolved) != expected_hash:
                errors.append(f"{stage_id} cache output hash mismatch: {relative}")

    status = "failed" if errors else ("passed_with_warnings" if warnings else "passed")
    return {
        "status": status,
        "run_id": state.get("run_id"),
        "execution_mode": mode,
        "state_revision": revision,
        "event_count": len(events),
        "errors": errors,
        "warnings": warnings,
    }


def _audit_production_task(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        parsed = PipelineState.from_object(state)
    except PlanValidationError as error:
        errors.append(str(error))
        parsed = None
    validator = ArtifactValidator(root)
    stage_inputs = StageInputValidator(root).validate_all()
    errors.extend(stage_inputs.errors)
    artifacts = state.get("artifacts")
    if isinstance(artifacts, dict):
        for artifact_id, record in artifacts.items():
            if not isinstance(record, dict):
                errors.append(f"registered artifact is invalid: {artifact_id}")
                continue
            path, digest = record.get("path"), record.get("sha256")
            if not isinstance(path, str):
                errors.append(f"registered artifact has no path: {artifact_id}")
                continue
            result = validator.validate_hash(path, str(digest))
            errors.extend(result.errors)
    else:
        errors.append("artifacts must be an object")
    gates = state.get("gate_status")
    if isinstance(gates, dict) and gates.get("gate5") == "approved":
        result = validator.validate_gate5_bundle(artifacts if isinstance(artifacts, dict) else {})
        errors.extend(result.errors)
    status = "failed" if errors else ("passed_with_warnings" if warnings else "passed")
    return {
        "status": status,
        "run_id": None if parsed is None else parsed.run_id,
        "execution_mode": state.get("execution_mode"),
        "state_revision": state.get("state_revision"),
        "event_count": len(read_jsonl_records(root / "pipeline_events.jsonl")),
        "errors": errors,
        "warnings": warnings,
    }


def _load_plan(workspace_root: Path, plan_path: Path) -> ExecutionPlan:
    workspace = workspace_root.resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("workspace root must be a directory")
    resolved_plan = plan_path.resolve(strict=True)
    if not _inside(resolved_plan, workspace):
        raise ValueError("plan path must remain inside workspace root")
    # Track B is intentionally unavailable until the manifest's G-A lock is lifted.
    try:
        raw_plan = json.loads(resolved_plan.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raw_plan = None
    if isinstance(raw_plan, dict) and raw_plan.get("execution_mode") == "track-b-production":
        _require_track_b_unlocked()
    return ExecutionPlan.from_json(
        resolved_plan.read_bytes(), workspace_root=workspace
    )


def _require_track_b_unlocked() -> None:
    manifest_path = Path(__file__).resolve().parents[2] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tracks = manifest.get("tracks", {}) if isinstance(manifest, dict) else {}
    if isinstance(tracks, dict) and tracks.get("track_b") == "locked_until_g_a":
        raise ValueError("Track B production is locked until G-A")


def _initialize_production_task(
    workspace_root: Path, task_dir: Path, reference: Path
) -> ProductionRunner:
    workspace = workspace_root.resolve(strict=True)
    requested_task = Path(task_dir)
    if requested_task.is_symlink():
        raise StorageError("task directory must not be a symlink")
    resolved_parent = requested_task.parent.resolve(strict=True)
    candidate = resolved_parent / requested_task.name
    if not _inside(candidate, workspace):
        raise StorageError("task directory must remain inside workspace root")
    source = Path(reference)
    if source.is_symlink():
        raise StorageError("reference input must not be a symlink")
    resolved_source = source.resolve(strict=True)
    if not resolved_source.is_file() or not _inside(resolved_source, workspace):
        raise StorageError("reference input must be a workspace file")
    candidate.mkdir()
    target = candidate / resolved_source.name
    try:
        shutil.copy2(resolved_source, target)
        runner = ProductionRunner(candidate, (ReferenceSplitAdapter(candidate, target),))
        runner.initialize()
        return runner
    except BaseException:
        if target.exists() and not target.is_symlink():
            target.unlink()
        if candidate.exists() and not any(candidate.iterdir()):
            candidate.rmdir()
        raise


def _production_runner(
    task_dir: Path,
    reference: Path,
    *,
    asset_root: Path | None = None,
    brief_path: Path | None = None,
    asset_profiles_path: Path | None = None,
    cache_path: Path | None = None,
    doubao_client_script: Path | None = None,
    runtime_config: ProductionRuntimeConfig | None = None,
) -> ProductionRunner:
    root = _task_root(task_dir)
    if runtime_config is not None:
        if any(
            value is not None
            for value in (
                asset_root,
                brief_path,
                asset_profiles_path,
                cache_path,
                doubao_client_script,
            )
        ):
            raise ValueError("runtime_config cannot be combined with individual runtime paths")
        return ProductionRunner.from_registry(
            root,
            build_real_registry(
                task_root=root,
                reference_path=Path(reference).resolve(strict=True),
                asset_root=runtime_config.asset_root,
                brief_path=runtime_config.brief_path,
                asset_profiles_path=runtime_config.asset_profiles_path,
                cache_path=runtime_config.cache_path,
                doubao_client_script=runtime_config.doubao_client_script,
                python_executable=runtime_config.python_executable,
                archive_root=runtime_config.archive_root,
            ),
        )
    runtime_values = (
        asset_root,
        brief_path,
        asset_profiles_path,
        cache_path,
        doubao_client_script,
    )
    if any(value is not None for value in runtime_values):
        if any(value is None for value in runtime_values):
            raise ValueError(
                "real production runner requires asset root, brief, asset profiles, "
                "cache, and Doubao client"
            )
        registry = build_real_registry(
            task_root=root,
            reference_path=Path(reference).resolve(strict=True),
            asset_root=Path(asset_root).resolve(strict=True),
            brief_path=Path(brief_path).resolve(strict=True),
            asset_profiles_path=Path(asset_profiles_path).resolve(strict=True),
            cache_path=Path(cache_path).resolve(strict=False),
            doubao_client_script=Path(doubao_client_script).resolve(strict=True),
        )
        return ProductionRunner.from_registry(root, registry)
    return ProductionRunner(root, (ReferenceSplitAdapter(root, reference),))


def _write_pair_runtime_config(
    task_dir: Path, *, asset_root: Path, doubao_client: Path, python_executable: str
) -> Path:
    config_path = task_dir / "production_runtime_config.json"
    payload = {
        "artifact_type": "production_runtime_config",
        "schema_version": "1.0.0",
        "reference_path": next(task_dir.glob("reference-*.mp4")).name,
        "asset_root": str(Path(asset_root).resolve(strict=True)),
        "brief_path": "project_brief.json",
        "asset_profiles_path": "asset_profiles.json",
        "cache_path": "cache/assets.sqlite3",
        "doubao_client_script": str(Path(doubao_client).resolve(strict=True)),
        "python_executable": python_executable,
    }
    from .storage import atomic_write_json

    atomic_write_json(config_path, payload)
    return config_path


def _pair_decision_file(decision_dir: Path | None, gate_id: str) -> Path | None:
    if decision_dir is None:
        return None
    candidate = decision_dir / f"{gate_id}.json"
    return candidate if candidate.is_file() else None


def _pending_pair_gate(task_dir: Path, state: Mapping[str, object]) -> str | None:
    gates = state.get("gate_status")
    if not isinstance(gates, Mapping):
        return None
    for gate_id, status in gates.items():
        if status != "awaiting_user":
            continue
        if gate_id == "gate5" and not (
            task_dir / "gate_review_packages" / "gate5.json"
        ).is_file():
            continue
        return str(gate_id)
    return None


def _pair_side_complete(state: Mapping[str, object]) -> bool:
    gates = state.get("gate_status")
    return isinstance(gates, Mapping) and gates.get("gate5") == "approved"


def _pair_side_halted(state: Mapping[str, object]) -> bool:
    gates = state.get("gate_status")
    return isinstance(gates, Mapping) and any(
        status in {"blocked", "stale", "failed"} for status in gates.values()
    )


def _gb_pair_status(
    cold: Mapping[str, object], hot: Mapping[str, object] | None
) -> tuple[str, str]:
    if hot is not None and isinstance(hot.get("gate_status"), Mapping):
        if hot["gate_status"].get("gate5") == "approved":
            return (
                "measured_pending_review",
                "V1 baseline and owner G-B threshold review remain outstanding",
            )
    if cold.get("status") == "awaiting_user" or (
        hot is not None and hot.get("status") == "awaiting_user"
    ):
        return (
            "awaiting_user",
            "fresh cold and hot Gate 5 approvals plus timing evidence are required",
        )
    return (
        "blocked",
        "fresh cold and hot Gate 5 approvals plus timing evidence are required",
    )


def _run_pair_side(
    *, task_dir: Path, runtime_config: Path, decision_dir: Path | None, actor: str,
    run_id: str,
) -> dict[str, object]:
    runner = _production_runner(
        task_dir,
        task_dir / next(task_dir.glob("reference-*.mp4")).name,
        runtime_config=ProductionRuntimeConfig.from_file(runtime_config),
    )
    state_path = task_dir / "pipeline_state.json"
    if state_path.is_file():
        existing_state = read_json_object(state_path)
        existing_run_id = existing_state.get("run_id")
        if not isinstance(existing_run_id, str) or not existing_run_id:
            raise ValueError("existing G-B task has no run_id")
        run_id = existing_run_id
        resume_run = True
    else:
        runner.initialize(run_id=run_id)
        resume_run = False
    service = ApprovalService(TaskStorage(task_dir))
    started = time.perf_counter()
    started_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    result = None
    approvals = 0
    for _ in range(len(runner.adapters) + 10):
        if _pair_side_complete(TaskStorage(task_dir).read_state()):
            break
        result = runner.run(resume=resume_run or approvals > 0)
        state = TaskStorage(task_dir).read_state()
        pending = _pending_pair_gate(task_dir, state)
        if not isinstance(pending, str):
            if _pair_side_halted(state):
                break
            stages = state.get("stage_status", {})
            if isinstance(stages, dict) and any(
                stages.get(stage_id) not in {"succeeded", "approved"}
                for stage_id in runner.adapters
            ):
                continue
            break
        decision = _pair_decision_file(decision_dir, pending)
        if decision is None:
            break
        package = task_dir / "gate_review_packages" / f"{pending}.json"
        service.approve(
            gate_id=pending,
            review_package_hash=_sha256(package),
            decision_file=decision,
            actor=actor,
        )
        approvals += 1
        if pending == "gate5":
            break
    else:
        raise RuntimeError("G-B pair runner did not reach a stable Gate or completion")
    state = TaskStorage(task_dir).read_state()
    ended_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    metric_records = read_jsonl_records(task_dir / "stage_metrics.jsonl")
    machine_seconds = round(
        sum(float(item.get("wall_seconds", 0.0)) for item in metric_records), 3
    )
    timing = {
        "machine_api_critical_path_seconds": {
            "status": "measured" if metric_records else "not_measured",
            "seconds": machine_seconds if metric_records else None,
            "started_at": started_at,
            "ended_at": ended_at,
            **({} if metric_records else {"reason": "no completed machine stages"}),
        },
        "human_wait_seconds": {
            "status": "not_measured", "seconds": None,
            "started_at": None, "ended_at": None,
            "reason": "fresh operator Gate timestamps are required",
        },
        "operator_touch_seconds": {
            "status": "not_measured", "seconds": None,
            "started_at": None, "ended_at": None,
            "reason": "operator activity log was not supplied",
        },
        "rework_seconds": {
            "status": "measured", "seconds": 0.0,
            "started_at": started_at, "ended_at": ended_at,
            "reason": "no Gate return or controlled mutation recorded in this invocation",
        },
        "retry_network_seconds": {
            "status": "not_measured", "seconds": None,
            "started_at": None, "ended_at": None,
            "reason": "TTS was not reached",
        },
        "gate_return_count": {
            "status": "measured", "seconds": 0,
            "started_at": started_at, "ended_at": ended_at,
        },
    }
    return {
        "run_id": run_id,
        "status": (
            "succeeded" if _pair_side_complete(state)
            else result.status if result is not None else "failed"
        ),
        "exit_code": (
            0 if _pair_side_complete(state)
            else result.exit_code if result is not None else EXIT_FAILED
        ),
        "state_revision": state.get("state_revision"),
        "gate_status": state.get("gate_status", {}),
        "approvals_recorded": approvals,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "timing": timing,
        "stage_metric_count": len(metric_records),
        "archive_suppressed": True,
    }


def run_gb_pair(args: argparse.Namespace) -> dict[str, object]:
    """Prepare and optionally execute an isolated, approval-bound G-B pair."""

    if args.doubao_client is None:
        raise ValueError("gb-pair requires --doubao-client")
    if args.resume_existing:
        validate_frozen_input(frozen_root=args.frozen_root, asset_root=args.asset_root)
        cold = Path(args.cold_task_dir).resolve(strict=True)
        hot = Path(args.hot_task_dir).resolve(strict=True)
        if cold.is_symlink() or hot.is_symlink() or cold == hot:
            raise MeasurementError("existing cold and hot task roots are invalid")
        snapshot = read_json_object(cold / "g_b_frozen_input_snapshot.json")
        if snapshot.get("artifact_type") != "g_b_frozen_input_snapshot":
            raise MeasurementError("existing cold task is not a frozen G-B task")
        pair = {
            "cold_task_root": str(cold),
            "hot_task_root": str(hot),
            "snapshot_sha256": _sha256(cold / "g_b_frozen_input_snapshot.json"),
            "approval_reuse": False,
            "copied_task_artifacts": False,
            "resumed": True,
        }
    else:
        pair = prepare_frozen_pair(
            frozen_root=args.frozen_root,
            cold_root=args.cold_task_dir,
            hot_root=args.hot_task_dir,
            asset_root=args.asset_root,
        )
        cold = Path(args.cold_task_dir).resolve(strict=True)
        hot = Path(args.hot_task_dir).resolve(strict=True)
    cold_config = _write_pair_runtime_config(
        cold,
        asset_root=args.asset_root,
        doubao_client=args.doubao_client,
        python_executable=args.python_executable,
    )
    hot_config = _write_pair_runtime_config(
        hot,
        asset_root=args.asset_root,
        doubao_client=args.doubao_client,
        python_executable=args.python_executable,
    )
    cold_result = _run_pair_side(
        task_dir=cold,
        runtime_config=cold_config,
        decision_dir=args.decision_dir,
        actor=args.actor,
        run_id=f"gb-cold-{int(time.time())}",
    )
    cache_result: dict[str, object] | None = None
    hot_result: dict[str, object] | None = None
    if cold_result.get("gate_status", {}).get("gate5") == "approved":
        if args.resume_existing and (hot / "pipeline_state.json").is_file():
            cache_result = reuse_existing_hot_cache(cold_root=cold, hot_root=hot)
        else:
            cache_result = clone_declared_cold_cache(cold_root=cold, hot_root=hot)
        hot_result = _run_pair_side(
            task_dir=hot,
            runtime_config=hot_config,
            decision_dir=args.decision_dir,
            actor=args.actor,
            run_id=f"gb-hot-{int(time.time())}",
        )
    else:
        cache_result = {"status": "not_ready", "reason": "cold run requires fresh approvals through Gate 5"}
    status, reason = _gb_pair_status(cold_result, hot_result)
    measurement = write_pair_measurement(
        pair_root=args.pair_root,
        cold=cold_result,
        hot=hot_result or {"status": "not_started"},
        status=status,
        reason=reason,
    )
    return {
        **pair,
        "status": status,
        "cold": cold_result,
        "hot": hot_result,
        "cache": cache_result,
        "measurement_path": str(measurement),
        "ordinary_track_b_enabled": False,
    }


def _emit(value: dict[str, Any], *, json_output: bool, command: str) -> None:
    if json_output:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return
    if command == "status":
        gate = (
            f"Gate {value['gate_id']}={value['gate_status']}"
            if value.get("gate_id")
            else "no pending Gate"
        )
        print(
            f"Task {value.get('run_id') or 'unknown'}: "
            f"{value.get('run_status') or value.get('current_stage') or 'unknown'}; {gate}"
        )
    elif command == "audit":
        print(
            f"Audit {value['status']}: {len(value['errors'])} errors, "
            f"{len(value['warnings'])} warnings"
        )
    elif command == "index-assets":
        print(
            f"Indexed {value['supported_files']} media files; "
            f"cache hits {value['cache_hits']}; unreadable {value['unreadable_files']}"
        )
    elif command in {
        "ga-prepare-review",
        "ga-record-decision",
        "ga-audit",
        "approve-gate",
    }:
        print(f"{command}: {value.get('status', 'passed')}")
    elif command == "gb-pair":
        print(
            f"G-B pair {value.get('status', 'unknown')}; "
            f"cold={value.get('cold', {}).get('status', 'unknown')}; "
            f"hot={value.get('hot', {}).get('status', 'not_started')}"
        )
    else:
        print(f"Fast Path {value['status']}")


def _emit_error(message: str, *, json_output: bool, status: str = "invalid") -> None:
    if json_output:
        print(json.dumps({"status": status, "error": message}, ensure_ascii=False))
    else:
        print(f"remixctl: {message}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    json_output = bool(getattr(args, "json", False))
    try:
        if args.command == "fast" or (
            args.command == "resume" and args.plan is not None
        ):
            if args.workspace_root is None or args.plan is None:
                raise ValueError("Fast Path resume requires --workspace-root and --plan")
            plan = _load_plan(args.workspace_root, args.plan)
            result = FastPathRunner(plan).run(resume=args.command == "resume")
            payload = dataclasses.asdict(result)
            _emit(payload, json_output=json_output, command=args.command)
            return result.exit_code
        production_commands = {
            "run",
            "stage",
            "resume",
            "production-run",
            "production-stage",
            "production-resume",
        }
        if args.command in {"init", *production_commands}:
            _require_track_b_unlocked()
            if args.command == "init":
                runner = _initialize_production_task(
                    args.workspace_root, args.task_dir, args.reference
                )
                payload = status_snapshot(runner.task_root)
                _emit(payload, json_output=json_output, command=args.command)
                return EXIT_OK
            runtime_config = (
                ProductionRuntimeConfig.from_file(args.runtime_config)
                if getattr(args, "runtime_config", None) is not None
                else None
            )
            reference = args.reference
            if reference is None and runtime_config is not None:
                reference = runtime_config.reference_path
            if args.task_dir is None or reference is None:
                raise ValueError("production command requires --task-dir and --reference or --runtime-config")
            runner = _production_runner(
                args.task_dir,
                reference,
                runtime_config=runtime_config,
            )
            result = runner.run(
                resume=args.command in {"resume", "production-resume"},
                stage_id=args.stage
                if args.command in {"stage", "production-stage"}
                else None,
            )
            payload = dataclasses.asdict(result)
            _emit(payload, json_output=json_output, command=args.command)
            return result.exit_code
        if args.command in {"status", "production-status"}:
            payload = status_snapshot(args.task_dir)
            _emit(payload, json_output=json_output, command="status")
            return EXIT_OK
        if args.command in {"audit", "production-audit"}:
            payload = audit_task(args.task_dir)
            _emit(payload, json_output=json_output, command="audit")
            return EXIT_FAILED if payload["status"] == "failed" else EXIT_OK
        if args.command == "ga-prepare-review":
            payload = prepare_review(args.task_dir, args.gate, args.artifact)
            _emit(payload, json_output=json_output, command=args.command)
            return EXIT_OK
        if args.command == "ga-record-decision":
            payload = record_decision(args.task_dir, args.gate, args.review_package, args.decision_file, args.actor)
            _emit(payload, json_output=json_output, command=args.command)
            return EXIT_OK
        if args.command == "ga-audit":
            payload = audit_ga(args.task_dir)
            _emit(payload, json_output=json_output, command=args.command)
            return EXIT_FAILED if payload["status"] == "failed" else EXIT_OK
        if args.command == "approve-gate":
            payload = ApprovalService(TaskStorage(args.task_dir)).approve(
                gate_id=args.gate,
                review_package_hash=args.review_package_hash,
                decision_file=args.decision_file,
                actor=args.actor,
            )
            _emit(payload, json_output=json_output, command=args.command)
            return EXIT_OK
        if args.command == "index-assets":
            summary = AssetIndexer(args.database).index(args.assets_root)
            payload = summary.to_dict()
            _emit(payload, json_output=json_output, command="index-assets")
            return EXIT_OK
        if args.command == "gb-pair":
            payload = run_gb_pair(args)
            _emit(payload, json_output=json_output, command="gb-pair")
            return EXIT_OK if payload["status"] == "measured_pending_review" else EXIT_AWAITING_USER
        raise ValueError(f"unsupported command: {args.command}")
    except AssetIndexPrerequisiteError as error:
        _emit_error(str(error), json_output=json_output, status="failed")
        return EXIT_FAILED
    except sqlite3.Error as error:
        _emit_error(str(error), json_output=json_output, status="failed")
        return EXIT_FAILED
    except ApprovalError as error:
        _emit_error(str(error), json_output=json_output, status="blocked")
        return EXIT_BLOCKED
    except MeasurementError as error:
        _emit_error(str(error), json_output=json_output, status="blocked")
        return EXIT_BLOCKED
    except (OSError, RuntimeError, StorageError, ValueError, PlanValidationError) as error:
        _emit_error(str(error), json_output=json_output)
        return EXIT_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
