"""Command-line entry point for the experimental Fast Path v0."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .asset_index import AssetIndexer, AssetIndexPrerequisiteError
from .approvals import ApprovalError, ApprovalService
from .contracts import ExecutionPlan, PlanValidationError
from .ga_evidence import audit_ga, prepare_review, record_decision
from .runner import FastPathRunner
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

    for command in ("fast", "resume"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--workspace-root", type=Path, required=True)
        subparser.add_argument("--plan", type=Path, required=True)
        subparser.add_argument("--json", action="store_true")

    for command in ("status", "audit"):
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
        manifest_path = Path(__file__).resolve().parents[2] / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tracks = manifest.get("tracks", {}) if isinstance(manifest, dict) else {}
        if (
            isinstance(tracks, dict)
            and tracks.get("track_b") == "locked_until_g_a"
        ):
            raise ValueError("Track B production is locked until G-A")
    return ExecutionPlan.from_json(
        resolved_plan.read_bytes(), workspace_root=workspace
    )


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
        if args.command in {"fast", "resume"}:
            plan = _load_plan(args.workspace_root, args.plan)
            result = FastPathRunner(plan).run(resume=args.command == "resume")
            payload = dataclasses.asdict(result)
            _emit(payload, json_output=json_output, command=args.command)
            return result.exit_code
        if args.command == "status":
            payload = status_snapshot(args.task_dir)
            _emit(payload, json_output=json_output, command="status")
            return EXIT_OK
        if args.command == "audit":
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
    except (OSError, RuntimeError, StorageError, ValueError, PlanValidationError) as error:
        _emit_error(str(error), json_output=json_output)
        return EXIT_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
