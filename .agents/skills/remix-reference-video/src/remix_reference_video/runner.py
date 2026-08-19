"""Gate-aware, resumable Fast Path v0 stage execution."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import shutil
import subprocess
import time
import uuid
from datetime import UTC, datetime
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .contracts import CommandResult, ExecutionPlan, PlanValidationError, StagePlan
from .orchestrator import ProductionOrchestrator, StageAdapter, dag_for_task, default_dag
from .review_view import ReviewViewBuilder
from .stage_input_validator import StageInputValidator
from .storage import (
    StorageError,
    TaskBusy,
    TaskStorage,
    atomic_write_json,
    read_json_object,
)


_SHELL_EXECUTABLES = frozenset(
    {
        "bash",
        "cmd",
        "csh",
        "dash",
        "fish",
        "env",
        "ksh",
        "powershell",
        "pwsh",
        "sh",
        "tcsh",
        "zsh",
    }
)

_CACHE_FACT_FIELDS = frozenset({
    "cache_source", "lookup_hit_count", "lookup_miss_count", "reused_record_count",
    "skipped", "evidence_paths", "failure_category",
})


def _metric_cache_facts(execution: Mapping[str, object] | None, *, cache_status: str) -> dict[str, object]:
    """Copy only declared adapter facts into the authoritative metric row."""
    facts: dict[str, object] = {"cache_status": cache_status}
    if not isinstance(execution, Mapping):
        return facts
    for field in _CACHE_FACT_FIELDS:
        value = execution.get(field)
        if value is not None:
            facts[field] = value
    if "cache_source" not in facts:
        facts["cache_source"] = "hot_lookup" if cache_status == "hit" else "none"
    return facts


def _failure_category(error: BaseException) -> str:
    text = str(error).lower()
    if any(token in text for token in ("network", "timeout", "http", "api")):
        return "network_api"
    if isinstance(error, (StorageError, ValueError)):
        return "validation"
    return "execution"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """Stop a timed-out stage and every child in its private process group."""

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def _run_stage_command(
    argv: tuple[str, ...], *, cwd: Path, timeout: float
) -> int:
    """Run one stage in an isolated process group without buffering logs."""

    process = subprocess.Popen(
        argv,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        shell=False,
        close_fds=True,
    )
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        raise


class FastPathRunner:
    """Execute one validated plan until completion or the next human Gate."""

    def __init__(self, plan: ExecutionPlan) -> None:
        self.plan = plan

    def run(self, *, resume: bool = False) -> CommandResult:
        request_id = str(uuid.uuid4())
        invocation_id = str(uuid.uuid4())
        if not self._task_root_is_stable():
            return self._detached_result(
                status="failed",
                exit_code=5,
                request_id=request_id,
                invocation_id=invocation_id,
                idempotency_key=self._idempotency_key(0, resume),
                revision=0,
                error_code="UNSAFE_TASK_ROOT",
            )
        try:
            existing = self._read_existing_state()
            self._validate_existing_state(existing)
        except (OSError, StorageError, ValueError):
            return self._detached_result(
                status="failed",
                exit_code=2,
                request_id=request_id,
                invocation_id=invocation_id,
                idempotency_key=self._idempotency_key(0, resume),
                revision=0,
                error_code="INVALID_PIPELINE_STATE",
            )
        before_revision = self._revision(existing)
        idempotency_key = self._idempotency_key(before_revision, resume)

        if existing and existing.get("execution_mode") == "manual-contract-only":
            return self._detached_result(
                status="blocked",
                exit_code=4,
                request_id=request_id,
                invocation_id=invocation_id,
                idempotency_key=idempotency_key,
                revision=before_revision,
                error_code="MANUAL_CONTRACT_ONLY",
            )
        if existing and existing.get("execution_mode") != self.plan.execution_mode:
            return self._detached_result(
                status="blocked",
                exit_code=4,
                request_id=request_id,
                invocation_id=invocation_id,
                idempotency_key=idempotency_key,
                revision=before_revision,
                error_code="EXECUTION_MODE_MISMATCH",
            )
        try:
            store = TaskStorage(self.plan.task_root)
        except (OSError, StorageError, ValueError):
            return self._detached_result(
                status="failed",
                exit_code=5,
                request_id=request_id,
                invocation_id=invocation_id,
                idempotency_key=idempotency_key,
                revision=before_revision,
                error_code="STORAGE_FAILURE",
            )
        try:
            with store.invocation_lock():
                if not self._task_root_is_stable():
                    return self._detached_result(
                        status="failed",
                        exit_code=5,
                        request_id=request_id,
                        invocation_id=invocation_id,
                        idempotency_key=idempotency_key,
                        revision=before_revision,
                        error_code="UNSAFE_TASK_ROOT",
                    )
                try:
                    existing = self._read_existing_state()
                    self._validate_existing_state(existing)
                except (OSError, StorageError, ValueError):
                    return self._detached_result(
                        status="failed",
                        exit_code=2,
                        request_id=request_id,
                        invocation_id=invocation_id,
                        idempotency_key=self._idempotency_key(0, resume),
                        revision=0,
                        error_code="INVALID_PIPELINE_STATE",
                    )
                before_revision = self._revision(existing)
                idempotency_key = self._idempotency_key(before_revision, resume)
                if existing and existing.get("execution_mode") == "manual-contract-only":
                    return self._detached_result(
                        status="blocked",
                        exit_code=4,
                        request_id=request_id,
                        invocation_id=invocation_id,
                        idempotency_key=idempotency_key,
                        revision=before_revision,
                        error_code="MANUAL_CONTRACT_ONLY",
                    )
                if existing and existing.get("execution_mode") != self.plan.execution_mode:
                    return self._detached_result(
                        status="blocked",
                        exit_code=4,
                        request_id=request_id,
                        invocation_id=invocation_id,
                        idempotency_key=idempotency_key,
                        revision=before_revision,
                        error_code="EXECUTION_MODE_MISMATCH",
                    )
                if resume and existing is None:
                    return self._detached_result(
                        status="failed",
                        exit_code=2,
                        request_id=request_id,
                        invocation_id=invocation_id,
                        idempotency_key=idempotency_key,
                        revision=0,
                        error_code="NO_STATE_TO_RESUME",
                    )
                if existing is None:
                    store.initialize_state(self._initial_state())
                store.reconcile_event_gap()
                before_revision = self._revision(store.read_state())
                state = self._update_run_status(store, "running")
                store.append_event(
                    {
                        "event_type": "run.resumed" if resume else "command.started",
                        "request_id": request_id,
                        "invocation_id": invocation_id,
                    },
                    state_revision=self._revision(state),
                )
                return self._run_stages(
                    store=store,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    before_revision=before_revision,
                )
        except TaskBusy:
            return self._detached_result(
                status="blocked",
                exit_code=4,
                request_id=request_id,
                invocation_id=invocation_id,
                idempotency_key=idempotency_key,
                revision=before_revision,
                error_code="TASK_LOCKED",
            )
        except (OSError, StorageError, ValueError) as error:
            return self._storage_failure_result(
                store,
                request_id=request_id,
                invocation_id=invocation_id,
                idempotency_key=idempotency_key,
                before_revision=before_revision,
                error=error,
            )

    def _run_stages(
        self,
        *,
        store: TaskStorage,
        request_id: str,
        invocation_id: str,
        idempotency_key: str,
        before_revision: int,
    ) -> CommandResult:
        all_cache_hits = True
        for stage in self.plan.stages:
            started = time.perf_counter()
            gate_result = self._check_required_gates(store, stage)
            if gate_result is not None:
                status, error_code, gate_id = gate_result
                elapsed = time.perf_counter() - started
                state = self._set_stage_and_run_status(
                    store, stage, status, status, error_code=error_code
                )
                store.append_event(
                    {
                        "event_type": "command.awaiting_user"
                        if status == "awaiting_user"
                        else "command.blocked",
                        "framework_stage_id": stage.framework_stage_id,
                        "execution_stage_id": stage.execution_stage_id,
                        "gate_id": gate_id,
                        "error_code": error_code,
                    },
                    state_revision=self._revision(state),
                )
                self._record_metric(store, stage, status, elapsed, cache_hit=False)
                return self._result(
                    store,
                    status=status,
                    exit_code=3 if status == "awaiting_user" else 4,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    before_revision=before_revision,
                    next_actions=(f"approve:{gate_id}",)
                    if status == "awaiting_user"
                    else (),
                    error_code=error_code,
                )

            if stage.stop_gate:
                stop_gate_status = self._gate_status(store, stage.stop_gate)
                if stop_gate_status in {"blocked", "failed", "stale"}:
                    elapsed = time.perf_counter() - started
                    state = self._set_stage_and_run_status(
                        store,
                        stage,
                        "blocked",
                        "blocked",
                        error_code="GATE_BLOCKED",
                    )
                    store.append_event(
                        {
                            "event_type": "command.blocked",
                            "framework_stage_id": stage.framework_stage_id,
                            "execution_stage_id": stage.execution_stage_id,
                            "gate_id": stage.stop_gate,
                            "error_code": "GATE_BLOCKED",
                        },
                        state_revision=self._revision(state),
                    )
                    self._record_metric(store, stage, "blocked", elapsed, cache_hit=False)
                    return self._result(
                        store,
                        status="blocked",
                        exit_code=4,
                        request_id=request_id,
                        invocation_id=invocation_id,
                        idempotency_key=idempotency_key,
                        before_revision=before_revision,
                        next_actions=(),
                        error_code="GATE_BLOCKED",
                    )

            missing_input = next(
                (path for path in stage.inputs if not path.is_file()), None
            )
            if missing_input is not None:
                return self._stage_failure(
                    store,
                    stage,
                    error_code="MISSING_INPUT",
                    elapsed=time.perf_counter() - started,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    before_revision=before_revision,
                )

            fingerprint = self.plan.input_fingerprint(stage.execution_stage_id)
            cache_record = self._cache_record(store.read_state(), stage)
            if stage.cache and self._cache_valid(stage, fingerprint, cache_record):
                elapsed = time.perf_counter() - started
                store.append_event(
                    {
                        "event_type": "command.cache_hit",
                        "framework_stage_id": stage.framework_stage_id,
                        "execution_stage_id": stage.execution_stage_id,
                        "input_fingerprint": fingerprint,
                    },
                    state_revision=self._revision(store.read_state()),
                )
                self._record_metric(
                    store, stage, "cache_hit", elapsed, cache_hit=True
                )
                if stage.stop_gate and not self._gate_approval_valid(
                    store.read_state(), stage.stop_gate
                ):
                    stop_gate_status = self._gate_status(store, stage.stop_gate)
                    if stop_gate_status in {"blocked", "failed", "stale"}:
                        state = self._set_stage_and_run_status(
                            store,
                            stage,
                            "blocked",
                            "blocked",
                            error_code="GATE_BLOCKED",
                        )
                        store.append_event(
                            {
                                "event_type": "command.blocked",
                                "framework_stage_id": stage.framework_stage_id,
                                "execution_stage_id": stage.execution_stage_id,
                                "gate_id": stage.stop_gate,
                                "error_code": "GATE_BLOCKED",
                            },
                            state_revision=self._revision(state),
                        )
                        self._record_metric(
                            store, stage, "blocked", elapsed, cache_hit=True
                        )
                        return self._result(
                            store,
                            status="blocked",
                            exit_code=4,
                            request_id=request_id,
                            invocation_id=invocation_id,
                            idempotency_key=idempotency_key,
                            before_revision=before_revision,
                            next_actions=(),
                            error_code="GATE_BLOCKED",
                        )
                    invalid_approval = stop_gate_status == "approved"
                    state = self._set_gate_wait(
                        store,
                        stage,
                        input_fingerprint=fingerprint,
                        output_hashes=cache_record.get("output_hashes", {}),
                    )
                    store.append_event(
                        {
                            "event_type": "command.awaiting_user",
                            "framework_stage_id": stage.framework_stage_id,
                            "execution_stage_id": stage.execution_stage_id,
                            "gate_id": stage.stop_gate,
                            "error_code": "GATE_APPROVAL_INVALID"
                            if invalid_approval
                            else None,
                        },
                        state_revision=self._revision(state),
                    )
                    return self._result(
                        store,
                        status="awaiting_user",
                        exit_code=3,
                        request_id=request_id,
                        invocation_id=invocation_id,
                        idempotency_key=idempotency_key,
                        before_revision=before_revision,
                        next_actions=(f"approve:{stage.stop_gate}",),
                        error_code="GATE_APPROVAL_INVALID"
                        if invalid_approval
                        else None,
                    )
                continue

            all_cache_hits = False
            executable = self._resolve_executable(stage.argv[0])
            if executable is None:
                return self._stage_failure(
                    store,
                    stage,
                    error_code="EXECUTABLE_NOT_FOUND",
                    elapsed=time.perf_counter() - started,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    before_revision=before_revision,
                )
            if any(not self._declared_output_is_safe(path) for path in stage.outputs):
                return self._stage_failure(
                    store,
                    stage,
                    error_code="UNSAFE_OUTPUT",
                    elapsed=time.perf_counter() - started,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    before_revision=before_revision,
                )
            output_signatures = {
                path: self._file_signature(path)
                if self._safe_output_path(path)
                else None
                for path in stage.outputs
            }
            state = self._set_stage_and_run_status(
                store, stage, "running", "running"
            )
            store.append_event(
                {
                    "event_type": "command.started",
                    "framework_stage_id": stage.framework_stage_id,
                    "execution_stage_id": stage.execution_stage_id,
                    "input_fingerprint": fingerprint,
                },
                state_revision=self._revision(state),
            )

            argv = (str(executable), *stage.argv[1:])
            try:
                process_exit_code = _run_stage_command(
                    argv,
                    cwd=self.plan.task_root,
                    timeout=stage.timeout_seconds,
                )
            except (subprocess.TimeoutExpired, OverflowError):
                return self._stage_failure(
                    store,
                    stage,
                    error_code="STAGE_TIMEOUT",
                    elapsed=time.perf_counter() - started,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    before_revision=before_revision,
                )
            except OSError:
                return self._stage_failure(
                    store,
                    stage,
                    error_code="STAGE_PROCESS_ERROR",
                    elapsed=time.perf_counter() - started,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    before_revision=before_revision,
                )
            if process_exit_code != 0:
                return self._stage_failure(
                    store,
                    stage,
                    error_code="STAGE_COMMAND_FAILED",
                    elapsed=time.perf_counter() - started,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    before_revision=before_revision,
                    process_exit_code=process_exit_code,
                )
            if any(not self._safe_output_path(path) for path in stage.outputs):
                return self._stage_failure(
                    store,
                    stage,
                    error_code="UNSAFE_OUTPUT"
                    if all(path.is_file() for path in stage.outputs)
                    else "MISSING_OUTPUT",
                    elapsed=time.perf_counter() - started,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    before_revision=before_revision,
                )
            if any(
                previous is not None and self._file_signature(path) == previous
                for path, previous in output_signatures.items()
            ):
                return self._stage_failure(
                    store,
                    stage,
                    error_code="OUTPUT_NOT_UPDATED",
                    elapsed=time.perf_counter() - started,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    before_revision=before_revision,
                )
            try:
                input_is_unchanged = (
                    self.plan.input_fingerprint(stage.execution_stage_id) == fingerprint
                )
            except (OSError, PlanValidationError):
                input_is_unchanged = False
            if not input_is_unchanged:
                return self._stage_failure(
                    store,
                    stage,
                    error_code="INPUT_MUTATED",
                    elapsed=time.perf_counter() - started,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    before_revision=before_revision,
                )
            output_hashes = {
                path.relative_to(self.plan.task_root).as_posix(): _sha256_file(path)
                for path in stage.outputs
            }
            elapsed = time.perf_counter() - started
            state = self._record_success(
                store, stage, fingerprint=fingerprint, output_hashes=output_hashes
            )
            store.append_event(
                {
                    "event_type": "command.succeeded",
                    "framework_stage_id": stage.framework_stage_id,
                    "execution_stage_id": stage.execution_stage_id,
                    "input_fingerprint": fingerprint,
                    "artifact_paths": sorted(output_hashes),
                },
                state_revision=self._revision(state),
            )
            self._record_metric(store, stage, "succeeded", elapsed, cache_hit=False)
            if stage.stop_gate:
                state = self._set_gate_wait(
                    store,
                    stage,
                    input_fingerprint=fingerprint,
                    output_hashes=output_hashes,
                )
                store.append_event(
                    {
                        "event_type": "command.awaiting_user",
                        "framework_stage_id": stage.framework_stage_id,
                        "execution_stage_id": stage.execution_stage_id,
                        "gate_id": stage.stop_gate,
                    },
                    state_revision=self._revision(state),
                )
                return self._result(
                    store,
                    status="awaiting_user",
                    exit_code=3,
                    request_id=request_id,
                    invocation_id=invocation_id,
                    idempotency_key=idempotency_key,
                    before_revision=before_revision,
                    next_actions=(f"approve:{stage.stop_gate}",),
                    error_code=None,
                )

        final_status = "cache_hit" if all_cache_hits else "succeeded"
        state = self._update_run_status(store, final_status)
        store.append_event(
            {"event_type": "command.cache_hit" if all_cache_hits else "command.succeeded"},
            state_revision=self._revision(state),
        )
        return self._result(
            store,
            status=final_status,
            exit_code=0,
            request_id=request_id,
            invocation_id=invocation_id,
            idempotency_key=idempotency_key,
            before_revision=before_revision,
            next_actions=(),
            error_code=None,
        )

    def _initial_state(self) -> dict[str, Any]:
        return {
            "artifact_type": "pipeline_state",
            "schema_id": "urn:capcut:remix-reference-video:artifact:pipeline-state",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "run_id": str(uuid.uuid4()),
            "execution_mode": self.plan.execution_mode,
            "state_revision": 0,
            "gate_status": {},
            "decisions": [],
            "fast_path": {
                "stage_status": {},
                "stage_cache": {},
                "gate_inputs": {},
                "run_status": "not_started",
            },
        }

    def _read_existing_state(self) -> dict[str, Any] | None:
        path = self.plan.task_root / "pipeline_state.json"
        if not path.exists():
            return None
        return read_json_object(path)

    def _validate_existing_state(
        self, state: Mapping[str, object] | None
    ) -> None:
        if state is None or state.get("execution_mode") == "manual-contract-only":
            return
        if state.get("execution_mode") != self.plan.execution_mode:
            return
        revision = state.get("state_revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise StorageError("state_revision must be a nonnegative integer")
        for field_name in ("gate_status", "fast_path"):
            value = state.get(field_name, {})
            if not isinstance(value, Mapping):
                raise StorageError(f"{field_name} must be an object")
        decisions = state.get("decisions", [])
        if not isinstance(decisions, list):
            raise StorageError("decisions must be an array")
        fast_path = state.get("fast_path", {})
        assert isinstance(fast_path, Mapping)
        for field_name in ("stage_status", "stage_cache", "gate_inputs"):
            value = fast_path.get(field_name, {})
            if not isinstance(value, Mapping):
                raise StorageError(f"fast_path.{field_name} must be an object")

    @staticmethod
    def _revision(state: Mapping[str, object] | None) -> int:
        if state is None:
            return 0
        value = state.get("state_revision", 0)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    def _idempotency_key(self, revision: int, resume: bool) -> str:
        value = {
            "execution_mode": self.plan.execution_mode,
            "task_root": self.plan.task_root.relative_to(
                self.plan.workspace_root
            ).as_posix(),
            "state_revision": revision,
            "resume": resume,
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _task_root_is_stable(self) -> bool:
        root = self.plan.task_root
        if root.is_symlink() or not root.is_dir():
            return False
        try:
            resolved = root.resolve(strict=True)
        except OSError:
            return False
        return resolved == root and _is_within(resolved, self.plan.workspace_root)

    def _resolve_executable(self, declared: str) -> Path | None:
        declared_path = Path(declared)
        if declared_path.name.lower() in _SHELL_EXECUTABLES:
            return None
        if declared_path.is_absolute():
            candidate = declared_path.resolve(strict=False)
        elif len(declared_path.parts) > 1:
            candidate = (self.plan.task_root / declared_path).resolve(strict=False)
            if not _is_within(candidate, self.plan.task_root):
                return None
        else:
            located = shutil.which(declared)
            if located is None:
                return None
            candidate = Path(located).resolve(strict=False)
        if candidate.name.lower() in _SHELL_EXECUTABLES:
            return None
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            return None
        return candidate

    @staticmethod
    def _gate_status(store: TaskStorage, gate_id: str) -> str:
        gates = store.read_state().get("gate_status", {})
        return gates.get(gate_id, "not_started") if isinstance(gates, dict) else "not_started"

    def _check_required_gates(
        self, store: TaskStorage, stage: StagePlan
    ) -> tuple[str, str, str] | None:
        state = store.read_state()
        for gate_id in stage.required_gates:
            gates = state.get("gate_status", {})
            status = gates.get(gate_id, "not_started") if isinstance(gates, dict) else "not_started"
            if status == "approved":
                if self._gate_approval_valid(state, gate_id):
                    continue
                return "awaiting_user", "GATE_APPROVAL_INVALID", gate_id
            if status in {"blocked", "failed"}:
                return "blocked", "GATE_BLOCKED", gate_id
            return "awaiting_user", "GATE_NOT_APPROVED", gate_id
        return None

    def _gate_approval_valid(self, state: Mapping[str, object], gate_id: str) -> bool:
        gates = state.get("gate_status", {})
        if not isinstance(gates, Mapping) or gates.get(gate_id) != "approved":
            return False
        fast_path = state.get("fast_path", {})
        gate_inputs = fast_path.get("gate_inputs", {}) if isinstance(fast_path, Mapping) else {}
        expected = gate_inputs.get(gate_id) if isinstance(gate_inputs, Mapping) else None
        expected_hashes = expected.get("output_hashes") if isinstance(expected, Mapping) else None
        if not isinstance(expected_hashes, Mapping) or not expected_hashes:
            return False
        decisions = state.get("decisions", [])
        if not isinstance(decisions, list):
            return False
        for decision in reversed(decisions):
            if not isinstance(decision, Mapping):
                continue
            decision_gate_id = decision.get("gate_id")
            decision_substate_id = decision.get("substate_id")
            if (
                (decision_gate_id is not None and not isinstance(decision_gate_id, str))
                or (
                    decision_substate_id is not None
                    and not isinstance(decision_substate_id, str)
                )
            ):
                continue
            if gate_id != decision_gate_id and gate_id != decision_substate_id:
                continue
            if decision.get("decision") != "approved":
                continue
            decision_status = decision.get("status")
            if not isinstance(decision_status, (str, type(None))):
                continue
            if decision_status in {"revoked", "stale", "superseded"}:
                continue
            actual_hashes = decision.get("input_hashes")
            if not isinstance(actual_hashes, Mapping):
                continue
            if all(
                isinstance(path, str)
                and isinstance(digest, str)
                and actual_hashes.get(path) == digest
                and self._current_output_hash(path) == digest
                for path, digest in expected_hashes.items()
            ):
                return True
        return False

    def _current_output_hash(self, relative: str) -> str | None:
        path = self.plan.task_root / relative
        if Path(relative).is_absolute() or not self._safe_output_path(path):
            return None
        try:
            return _sha256_file(path)
        except OSError:
            return None

    def _cache_record(
        self, state: Mapping[str, object], stage: StagePlan
    ) -> Mapping[str, object] | None:
        fast_path = state.get("fast_path")
        if not isinstance(fast_path, Mapping):
            return None
        records = fast_path.get("stage_cache")
        if not isinstance(records, Mapping):
            return None
        record = records.get(stage.execution_stage_id)
        return record if isinstance(record, Mapping) else None

    def _cache_valid(
        self,
        stage: StagePlan,
        fingerprint: str,
        record: Mapping[str, object] | None,
    ) -> bool:
        if record is None or record.get("input_fingerprint") != fingerprint:
            return False
        recorded_outputs = record.get("output_hashes")
        if not isinstance(recorded_outputs, Mapping):
            return False
        expected_paths = {
            path.relative_to(self.plan.task_root).as_posix(): path for path in stage.outputs
        }
        if set(recorded_outputs) != set(expected_paths):
            return False
        for relative, path in expected_paths.items():
            if not self._safe_output_path(path):
                return False
            digest = recorded_outputs.get(relative)
            if not isinstance(digest, str) or _sha256_file(path) != digest:
                return False
        return True

    @staticmethod
    def _file_signature(path: Path) -> tuple[int, int, int]:
        stat = path.stat()
        return (stat.st_size, stat.st_mtime_ns, stat.st_ino)

    def _safe_output_path(self, path: Path) -> bool:
        if path.is_symlink() or not path.is_file():
            return False
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            return False
        return _is_within(resolved, self.plan.task_root)

    def _declared_output_is_safe(self, path: Path) -> bool:
        """Check the resolved output destination before starting a child."""

        if path.is_symlink():
            return False
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            return False
        return _is_within(resolved, self.plan.task_root)

    @staticmethod
    def _update_run_status(store: TaskStorage, status: str) -> dict[str, Any]:
        def transform(state: dict[str, Any]) -> dict[str, Any]:
            fast_path = state.setdefault("fast_path", {})
            fast_path["run_status"] = status
            return state

        return store.update_state(transform)

    @staticmethod
    def _set_stage_and_run_status(
        store: TaskStorage,
        stage: StagePlan,
        stage_status: str,
        run_status: str,
        *,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        def transform(state: dict[str, Any]) -> dict[str, Any]:
            fast_path = state.setdefault("fast_path", {})
            stages = fast_path.setdefault("stage_status", {})
            stages[stage.execution_stage_id] = {
                "framework_stage_id": stage.framework_stage_id,
                "status": stage_status,
                "error_code": error_code,
            }
            fast_path["run_status"] = run_status
            return state

        return store.update_state(transform)

    def _record_success(
        self,
        store: TaskStorage,
        stage: StagePlan,
        *,
        fingerprint: str,
        output_hashes: Mapping[str, str],
    ) -> dict[str, Any]:
        def transform(state: dict[str, Any]) -> dict[str, Any]:
            fast_path = state.setdefault("fast_path", {})
            statuses = fast_path.setdefault("stage_status", {})
            statuses[stage.execution_stage_id] = {
                "framework_stage_id": stage.framework_stage_id,
                "status": "succeeded",
                "error_code": None,
            }
            cache = fast_path.setdefault("stage_cache", {})
            cache[stage.execution_stage_id] = {
                "input_fingerprint": fingerprint,
                "output_hashes": dict(output_hashes),
            }
            return state

        return store.update_state(transform)

    def _set_gate_wait(
        self,
        store: TaskStorage,
        stage: StagePlan,
        *,
        input_fingerprint: str,
        output_hashes: object,
    ) -> dict[str, Any]:
        assert stage.stop_gate is not None
        if not isinstance(output_hashes, Mapping):
            raise StorageError("gate output_hashes must be a mapping")

        current_index = next(
            index
            for index, planned in enumerate(self.plan.stages)
            if planned.execution_stage_id == stage.execution_stage_id
        )
        downstream_stages = self.plan.stages[current_index + 1 :]
        for downstream in downstream_stages:
            for path in downstream.outputs:
                if self._safe_output_path(path):
                    path.unlink()

        def transform(state: dict[str, Any]) -> dict[str, Any]:
            gate_status = state.setdefault("gate_status", {})
            gate_status[stage.stop_gate] = "awaiting_user"
            gate_inputs = state.setdefault("fast_path", {}).setdefault("gate_inputs", {})
            downstream_gate_ids = {
                planned.stop_gate
                for planned in downstream_stages
                if planned.stop_gate
            }
            decisions = state.setdefault("decisions", [])
            for gate_id in downstream_gate_ids:
                if gate_status.get(gate_id) == "approved":
                    gate_status[gate_id] = "stale"
                for decision in decisions:
                    if not isinstance(decision, dict):
                        continue
                    if decision.get("gate_id") == gate_id or decision.get("substate_id") == gate_id:
                        if decision.get("decision") == "approved":
                            decision["status"] = "stale"
            fast_path = state.setdefault("fast_path", {})
            gate_inputs = fast_path.setdefault("gate_inputs", gate_inputs)
            stage_cache = fast_path.setdefault("stage_cache", {})
            for downstream in downstream_stages:
                stage_cache.pop(downstream.execution_stage_id, None)
            gate_inputs[stage.stop_gate] = {
                "execution_stage_id": stage.execution_stage_id,
                "input_fingerprint": input_fingerprint,
                "output_hashes": dict(output_hashes),
            }
            fast_path["run_status"] = "awaiting_user"
            return state

        return store.update_state(transform)

    @staticmethod
    def _record_metric(
        store: TaskStorage,
        stage: StagePlan,
        status: str,
        elapsed: float,
        *,
        cache_hit: bool,
        process_exit_code: int | None = None,
    ) -> None:
        metric: dict[str, object] = {
            "framework_stage_id": stage.framework_stage_id,
            "execution_stage_id": stage.execution_stage_id,
            "status": status,
            "elapsed_seconds": round(max(elapsed, 0.0), 6),
            "cache_hit": cache_hit,
        }
        if process_exit_code is not None:
            metric["process_exit_code"] = process_exit_code
        store.append_metric(metric)

    def _stage_failure(
        self,
        store: TaskStorage,
        stage: StagePlan,
        *,
        error_code: str,
        elapsed: float,
        request_id: str,
        invocation_id: str,
        idempotency_key: str,
        before_revision: int,
        process_exit_code: int | None = None,
    ) -> CommandResult:
        state = self._set_stage_and_run_status(
            store, stage, "failed", "failed", error_code=error_code
        )
        store.append_event(
            {
                "event_type": "command.failed",
                "framework_stage_id": stage.framework_stage_id,
                "execution_stage_id": stage.execution_stage_id,
                "error_code": error_code,
            },
            state_revision=self._revision(state),
        )
        self._record_metric(
            store,
            stage,
            "failed",
            elapsed,
            cache_hit=False,
            process_exit_code=process_exit_code,
        )
        return self._result(
            store,
            status="failed",
            exit_code=5,
            request_id=request_id,
            invocation_id=invocation_id,
            idempotency_key=idempotency_key,
            before_revision=before_revision,
            next_actions=("resume",),
            error_code=error_code,
        )

    def _storage_failure_result(
        self,
        store: TaskStorage,
        *,
        request_id: str,
        invocation_id: str,
        idempotency_key: str,
        before_revision: int,
        error: Exception,
    ) -> CommandResult:
        try:
            state = self._update_run_status(store, "failed")
            store.append_event(
                {"event_type": "command.failed", "error_code": "STORAGE_FAILURE"},
                state_revision=self._revision(state),
            )
            return self._result(
                store,
                status="failed",
                exit_code=5,
                request_id=request_id,
                invocation_id=invocation_id,
                idempotency_key=idempotency_key,
                before_revision=before_revision,
                next_actions=("audit",),
                error_code="STORAGE_FAILURE",
            )
        except Exception:
            return self._detached_result(
                status="failed",
                exit_code=5,
                request_id=request_id,
                invocation_id=invocation_id,
                idempotency_key=idempotency_key,
                revision=before_revision,
                error_code="STORAGE_FAILURE",
            )

    @staticmethod
    def _result(
        store: TaskStorage,
        *,
        status: str,
        exit_code: int,
        request_id: str,
        invocation_id: str,
        idempotency_key: str,
        before_revision: int,
        next_actions: tuple[str, ...],
        error_code: str | None,
    ) -> CommandResult:
        state = store.read_state()
        events = store.read_events()
        sequence = events[-1]["sequence"] if events else 0
        return CommandResult(
            status=status,
            exit_code=exit_code,
            request_id=request_id,
            invocation_id=invocation_id,
            idempotency_key=idempotency_key,
            state_revision_before=before_revision,
            state_revision_after=FastPathRunner._revision(state),
            event_sequence=sequence,
            next_actions=next_actions,
            error_code=error_code,
        )

    @staticmethod
    def _detached_result(
        *,
        status: str,
        exit_code: int,
        request_id: str,
        invocation_id: str,
        idempotency_key: str,
        revision: int,
        error_code: str,
    ) -> CommandResult:
        return CommandResult(
            status=status,
            exit_code=exit_code,
            request_id=request_id,
            invocation_id=invocation_id,
            idempotency_key=idempotency_key,
            state_revision_before=revision,
            state_revision_after=revision,
            event_sequence=0,
            next_actions=(),
            error_code=error_code,
        )


class ProductionRunner:
    """Run registered native adapters through the authoritative production DAG."""

    def __init__(self, task_root: Path, adapters: tuple[StageAdapter, ...], dag: object | None = None) -> None:
        self.task_root = Path(task_root).resolve(strict=True)
        self.adapters = {adapter.execution_stage_id: adapter for adapter in adapters}
        if len(self.adapters) != len(adapters):
            raise StorageError("production adapter stage ids must be unique")
        self.orchestrator = ProductionOrchestrator(tuple(dag) if dag is not None else default_dag())

    @classmethod
    def from_registry(cls, task_root: Path, registry: object) -> "ProductionRunner":
        """Build a runner from a DAG-validated native adapter registry."""

        adapters = getattr(registry, "adapters", None)
        if not callable(adapters):
            raise StorageError("native registry must expose adapters()")
        return cls(task_root, tuple(adapters()), dag=dag_for_task(task_root))

    def initialize(self, *, run_id: str | None = None) -> dict[str, Any]:
        store = TaskStorage(self.task_root)
        return store.initialize_state(
            {
                "artifact_type": "pipeline_state",
                "schema_id": "urn:capcut:remix-reference-video:artifact:pipeline-state",
                "schema_version": "1.0.0",
                "contract_version": "2.0.0-alpha.1",
                "skill_version": "2.0.0-alpha.1",
                "execution_mode": "track-b-production",
                "run_id": run_id or str(uuid.uuid4()),
                "state_revision": 0,
                "active_stage": None,
                "active_command": None,
                "stage_status": {"init": "succeeded"},
                "gate_status": {
                    "gate1": "not_ready",
                    "gate2": "not_ready",
                    "gate3_material_selection": "not_ready",
                    "gate3_evidence_closure": "not_ready",
                    "gate3": "not_ready",
                    "gate4_pre_generation": "not_ready",
                    "gate4_post_generation": "not_ready",
                    "gate4": "not_ready",
                    "gate5": "not_ready",
                },
                "decisions": [],
                "artifacts": {},
                "blockers": [],
                "cache_summary": {},
            }
        )

    def run(self, *, resume: bool = False, stage_id: str | None = None) -> CommandResult:
        request_id = str(uuid.uuid4())
        invocation_id = str(uuid.uuid4())
        store = TaskStorage(self.task_root)
        state = store.read_state()
        before = self._revision(state)
        idempotency_key = hashlib.sha256(
            f"{state.get('run_id')}:{before}:{resume}:{stage_id or 'run'}".encode()
        ).hexdigest()
        pending = self._pending_gate(state)
        if pending is not None:
            return self._result(
                store,
                status="awaiting_user",
                exit_code=3,
                request_id=request_id,
                invocation_id=invocation_id,
                idempotency_key=idempotency_key,
                before=before,
                next_actions=(f"approve:{pending}",),
            )
        ready = [
            node
            for node in self.orchestrator.ready_nodes(state, retry_failed=resume)
            if node.node_id in self.adapters
        ]
        if stage_id is not None:
            ready = [node for node in ready if node.node_id == stage_id]
            if not ready:
                raise StorageError(f"production stage is not ready: {stage_id}")
        if not ready:
            return self._result(
                store,
                status="succeeded",
                exit_code=0,
                request_id=request_id,
                invocation_id=invocation_id,
                idempotency_key=idempotency_key,
                before=before,
            )
        node = ready[0]
        adapter = self.adapters[node.node_id]
        attempt = self.orchestrator.new_attempt(node.node_id)
        started_at = time.perf_counter()
        with store.invocation_lock():
            running = store.update_state(
                lambda current: current
                | {
                    "active_stage": node.node_id,
                    "active_command": "resume" if resume else ("stage" if stage_id else "run"),
                    "stage_status": {**current["stage_status"], node.node_id: "running"},
                    "blockers": [
                        blocker
                        for blocker in current.get("blockers", [])
                        if not (
                            blocker.get("category") == "stage_execution_failed"
                            and blocker.get("stage_id") == node.node_id
                        )
                    ],
                },
                expected_revision=before,
            )
            store.append_event(
                {
                    "event_type": "command.started",
                    "execution_stage_id": node.node_id,
                    "attempt_id": attempt.attempt_id,
                },
                state_revision=self._revision(running),
            )
            try:
                handoff = self.task_root / "stage_inputs" / f"{node.node_id}.json"
                if handoff.exists() or handoff.is_symlink():
                    validation = StageInputValidator(self.task_root).validate(
                        handoff, expected_stage_id=node.node_id
                    )
                    if not validation.valid:
                        raise StorageError(
                            "invalid stage input: " + "; ".join(validation.errors)
                        )
                execution = adapter.execute(attempt_id=attempt.attempt_id)
                review_artifacts = self._seal_gate_review_package(store, node, adapter)
                artifacts = {**self._artifact_records(adapter), **review_artifacts}
            except BaseException as error:
                elapsed = time.perf_counter() - started_at
                failed = store.update_state(
                    lambda current: current
                    | {
                        "active_stage": node.node_id,
                        "active_command": None,
                        "stage_status": {**current["stage_status"], node.node_id: "failed"},
                        "blockers": [
                            *current.get("blockers", []),
                            {"category": "stage_execution_failed", "stage_id": node.node_id, "detail": str(error)},
                        ],
                    }
                )
                store.append_event(
                    {"event_type": "command.failed", "execution_stage_id": node.node_id, "attempt_id": attempt.attempt_id, "failure_category": _failure_category(error)},
                    state_revision=self._revision(failed),
                )
                store.append_metric(
                    {
                        "execution_stage_id": node.node_id,
                        "attempt_id": attempt.attempt_id,
                        "status": "failed",
                        "wall_seconds": elapsed,
                        **_metric_cache_facts(None, cache_status="miss"),
                        "failure_category": _failure_category(error),
                    }
                )
                raise
            stop_gate = node.stop_gate or execution.get("stop_gate")
            execution_state = execution.get("state_changes")
            state_changes = dict(execution_state) if isinstance(execution_state, Mapping) else {}
            succeeded = store.update_state(
                lambda current: current
                | {
                    "active_stage": node.node_id,
                    "active_command": None,
                    "stage_status": {**current["stage_status"], node.node_id: "succeeded"},
                    "gate_status": (
                        {**current["gate_status"], str(stop_gate): "awaiting_user"}
                        if stop_gate
                        else current["gate_status"]
                    ),
                    "artifacts": {**current["artifacts"], **artifacts},
                    "cache_summary": {
                        **current["cache_summary"],
                        node.node_id: {
                            "status": execution.get("status"),
                            "fingerprint": adapter.cache_fingerprint(),
                        },
                    },
                }
                | state_changes
            )
            store.append_event(
                {
                    "event_type": "command.awaiting_user" if stop_gate else "command.succeeded",
                    "execution_stage_id": node.node_id,
                    **({"gate_id": stop_gate} if stop_gate else {}),
                },
                state_revision=self._revision(succeeded),
            )
            store.append_metric(
                {
                    "execution_stage_id": node.node_id,
                    "attempt_id": attempt.attempt_id,
                    "status": "succeeded",
                    "wall_seconds": time.perf_counter() - started_at,
                    **_metric_cache_facts(
                        execution,
                        cache_status="hit" if execution.get("status") == "cache_hit" else "miss",
                    ),
                }
            )
        return self._result(
            store,
            status="awaiting_user" if stop_gate else "succeeded",
            exit_code=3 if stop_gate else 0,
            request_id=request_id,
            invocation_id=invocation_id,
            idempotency_key=idempotency_key,
            before=before,
            next_actions=(f"approve:{stop_gate}",) if stop_gate else (),
        )

    def _seal_gate_review_package(
        self, store: TaskStorage, node: object, adapter: StageAdapter
    ) -> dict[str, dict[str, str]]:
        stop_gate = getattr(node, "stop_gate", None)
        if not isinstance(stop_gate, str) or not stop_gate:
            return {}
        package_path = self.task_root / "gate_review_packages" / f"{stop_gate}.json"
        if not package_path.is_file() or package_path.is_symlink():
            raise StorageError(f"missing Gate review package: {package_path.name}")
        package = read_json_object(package_path)
        current = store.read_state()
        predicted_revision = self._revision(current) + 1
        input_hashes = package.get("input_hashes")
        if not isinstance(input_hashes, Mapping) or not input_hashes:
            input_hashes = {}
            for declared in adapter.declared_outputs():
                paths = sorted(declared.rglob("*")) if declared.is_dir() else [declared]
                for path in paths:
                    if not path.is_file() or path.is_symlink() or path == package_path:
                        continue
                    input_hashes[path.relative_to(self.task_root).as_posix()] = _sha256_file(path)
        package.update(
            {
                "run_id": current.get("run_id"),
                "gate_id": stop_gate,
                "created_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "state_revision": predicted_revision,
                "input_hashes": dict(input_hashes),
            }
        )
        atomic_write_json(package_path, package)
        projected_state = {
            **current,
            "state_revision": predicted_revision,
            "gate_status": {**dict(current.get("gate_status", {})), stop_gate: "awaiting_user"},
        }
        snapshot_paths = ReviewViewBuilder(self.task_root).write_snapshot(
            stop_gate, projected_state=projected_state
        )
        records: dict[str, dict[str, str]] = {}
        for path_text in snapshot_paths.values():
            path = Path(path_text)
            relative = path.relative_to(self.task_root).as_posix()
            records[relative] = {"path": relative, "sha256": _sha256_file(path)}
        return records

    def _artifact_records(self, adapter: StageAdapter) -> dict[str, dict[str, str]]:
        records: dict[str, dict[str, str]] = {}
        for declared in adapter.declared_outputs():
            paths = sorted(declared.rglob("*")) if declared.is_dir() else [declared]
            for path in paths:
                if not path.is_file() or path.is_symlink():
                    continue
                relative = path.relative_to(self.task_root).as_posix()
                records[relative] = {"path": relative, "sha256": _sha256_file(path)}
        return records

    def _pending_gate(self, state: Mapping[str, object]) -> str | None:
        gates = state.get("gate_status")
        if not isinstance(gates, Mapping):
            raise StorageError("gate_status must be an object")
        for gate_id, status in gates.items():
            if gate_id in {"gate3", "gate4"}:
                continue
            if status in {"awaiting_user", "blocked", "stale", "rejected"}:
                if gate_id == "gate5" and status == "awaiting_user":
                    # RenderAdapter may mark Gate 5 awaiting before the DAG's
                    # package-builder node has sealed the review package.
                    # The package itself is the actual stop point.
                    if not (
                        self.task_root / "gate_review_packages" / "gate5.json"
                    ).is_file():
                        continue
                return str(gate_id)
        return None

    @staticmethod
    def _revision(state: Mapping[str, object]) -> int:
        revision = state.get("state_revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise StorageError("state_revision must be a nonnegative integer")
        return revision

    @staticmethod
    def _result(
        store: TaskStorage,
        *,
        status: str,
        exit_code: int,
        request_id: str,
        invocation_id: str,
        idempotency_key: str,
        before: int,
        next_actions: tuple[str, ...] = (),
    ) -> CommandResult:
        state = store.read_state()
        events = store.read_events()
        return CommandResult(
            status=status,
            exit_code=exit_code,
            request_id=request_id,
            invocation_id=invocation_id,
            idempotency_key=idempotency_key,
            state_revision_before=before,
            state_revision_after=ProductionRunner._revision(state),
            event_sequence=0 if not events else int(events[-1]["sequence"]),
            next_actions=next_actions,
            error_code=None,
        )
