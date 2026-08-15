"""Immutable, validated contracts shared by Fast Path v0 components."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from types import MappingProxyType
from typing import Any, Self

EXECUTION_MODE = "fast-path-v0"
PRODUCTION_EXECUTION_MODE = "track-b-production"
MAX_STAGE_TIMEOUT_SECONDS = 86_400.0
CANONICAL_GATE_ORDER = (
    "gate1",
    "gate2",
    "gate3_material_selection",
    "gate3_evidence_closure",
    "gate4_pre_generation",
    "gate4_post_generation",
    "gate5",
)
CANONICAL_GATE_IDS = frozenset(CANONICAL_GATE_ORDER)
PRODUCTION_GATE_IDS = CANONICAL_GATE_IDS | {"gate3", "gate4"}
WORK_STATUSES = frozenset(
    {"not_started", "running", "succeeded", "blocked", "failed", "stale"}
)
GATE_STATUSES = frozenset(
    {"not_ready", "awaiting_user", "approved", "rejected", "blocked", "stale"}
)
FRAMEWORK_STAGE_ORDER = (
    "performance_proven_video",
    "blueprint",
    "controlled_mutation",
    "retrieval",
    "reconstruction",
)
FRAMEWORK_STAGE_IDS = frozenset(
    FRAMEWORK_STAGE_ORDER
)
_FRAMEWORK_ENTRY_GATES = {
    "performance_proven_video": frozenset(),
    "blueprint": frozenset({"gate1"}),
    "controlled_mutation": frozenset({"gate1"}),
    "retrieval": frozenset({"gate2"}),
    "reconstruction": frozenset(
        {"gate3_material_selection", "gate3_evidence_closure"}
    ),
}
_RESERVED_TASK_OUTPUTS = frozenset(
    {
        "pipeline_state.json",
        "pipeline_events.jsonl",
        "stage_metrics.jsonl",
        ".fast_path.lock",
    }
)

_PLAN_FIELDS = frozenset({"task_root", "execution_mode", "stages"})
_STAGE_FIELDS = frozenset(
    {
        "execution_stage_id",
        "framework_stage_id",
        "argv",
        "inputs",
        "outputs",
        "required_gates",
        "stop_gate",
        "timeout_seconds",
        "cache",
    }
)


class PlanValidationError(ValueError):
    """Raised when a Fast Path contract is malformed or unsafe."""


def _status_map(
    value: object,
    *,
    field_name: str,
    allowed_statuses: frozenset[str],
    allowed_ids: frozenset[str] | None = None,
) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise PlanValidationError(f"{field_name} must be an object")
    parsed: dict[str, str] = {}
    for raw_id, raw_status in value.items():
        item_id = _require_nonempty_string(raw_id, f"{field_name} id")
        if allowed_ids is not None and item_id not in allowed_ids:
            raise PlanValidationError(f"{field_name} contains unknown id: {item_id}")
        status = _require_nonempty_string(raw_status, f"{field_name}.{item_id}")
        if status not in allowed_statuses:
            raise PlanValidationError(
                f"{field_name}.{item_id} has unsupported status: {status}"
            )
        parsed[item_id] = status
    return MappingProxyType(parsed)


@dataclass(frozen=True, slots=True)
class PipelineState:
    """Strict authoritative state used only by Track B production tasks."""

    execution_mode: str
    run_id: str
    state_revision: int
    active_stage: str | None
    active_command: str | None
    stage_status: Mapping[str, str]
    gate_status: Mapping[str, str]
    decisions: tuple[object, ...]
    artifacts: Mapping[str, object]
    blockers: tuple[object, ...]
    cache_summary: Mapping[str, object]

    @classmethod
    def from_object(cls, value: Mapping[str, object]) -> Self:
        if not isinstance(value, Mapping):
            raise PlanValidationError("pipeline state must be an object")
        execution_mode = _require_nonempty_string(
            value.get("execution_mode"), "execution_mode"
        )
        if execution_mode != PRODUCTION_EXECUTION_MODE:
            raise PlanValidationError(
                f"execution_mode must be exactly {PRODUCTION_EXECUTION_MODE!r}"
            )
        run_id = _require_nonempty_string(value.get("run_id"), "run_id")
        revision = _require_nonnegative_integer(
            value.get("state_revision"), "state_revision"
        )
        active_stage = cls._optional_string(value.get("active_stage"), "active_stage")
        active_command = cls._optional_string(
            value.get("active_command"), "active_command"
        )
        decisions = value.get("decisions")
        artifacts = value.get("artifacts")
        blockers = value.get("blockers")
        cache_summary = value.get("cache_summary")
        if not isinstance(decisions, list):
            raise PlanValidationError("decisions must be an array")
        if not isinstance(artifacts, Mapping):
            raise PlanValidationError("artifacts must be an object")
        if not isinstance(blockers, list):
            raise PlanValidationError("blockers must be an array")
        if not isinstance(cache_summary, Mapping):
            raise PlanValidationError("cache_summary must be an object")
        return cls(
            execution_mode=execution_mode,
            run_id=run_id,
            state_revision=revision,
            active_stage=active_stage,
            active_command=active_command,
            stage_status=_status_map(
                value.get("stage_status"),
                field_name="stage_status",
                allowed_statuses=WORK_STATUSES,
            ),
            gate_status=_status_map(
                value.get("gate_status"),
                field_name="gate_status",
                allowed_statuses=GATE_STATUSES,
                allowed_ids=PRODUCTION_GATE_IDS,
            ),
            decisions=tuple(decisions),
            artifacts=MappingProxyType(dict(artifacts)),
            blockers=tuple(blockers),
            cache_summary=MappingProxyType(dict(cache_summary)),
        )

    @staticmethod
    def _optional_string(value: object, field_name: str) -> str | None:
        if value is None:
            return None
        return _require_nonempty_string(value, field_name)


def project_runtime_state(value: Mapping[str, object]) -> dict[str, object]:
    """Project old alpha state without silently upgrading it to production."""

    mode = value.get("execution_mode")
    if mode == PRODUCTION_EXECUTION_MODE:
        state = PipelineState.from_object(value)
        return {
            "supported": True,
            "execution_mode": state.execution_mode,
            "run_id": state.run_id,
            "state_revision": state.state_revision,
            "active_stage": state.active_stage,
            "active_command": state.active_command,
        }
    return {
        "supported": False,
        "execution_mode": mode if isinstance(mode, str) else None,
        "run_id": value.get("run_id") if isinstance(value.get("run_id"), str) else None,
        "state_revision": None,
        "active_stage": None,
        "active_command": None,
    }


def _require_nonempty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanValidationError(f"{field_name} must be a nonempty string")
    if "\x00" in value:
        raise PlanValidationError(f"{field_name} must not contain NUL bytes")
    return value


def _require_nonnegative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PlanValidationError(f"{field_name} must be a nonnegative integer")
    return value


def _require_positive_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanValidationError(f"{field_name} must be a positive finite number")
    try:
        parsed = float(value)
    except OverflowError as error:
        raise PlanValidationError(
            f"{field_name} must be a positive finite number"
        ) from error
    if (
        not math.isfinite(parsed)
        or parsed <= 0
        or parsed > MAX_STAGE_TIMEOUT_SECONDS
    ):
        raise PlanValidationError(f"{field_name} must be a positive finite number")
    return parsed


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _resolved_under(path: Path, root: Path, field_name: str, root_name: str) -> Path:
    resolved = path.resolve(strict=False)
    if not _is_within(resolved, root):
        raise PlanValidationError(f"{field_name} path must remain within {root_name}")
    return resolved


def _resolve_declared_path(
    value: object,
    *,
    root: Path,
    field_name: str,
    root_name: str,
) -> Path:
    raw_path = _require_nonempty_string(value, field_name)
    declared = Path(raw_path)
    if declared.is_absolute() or PureWindowsPath(raw_path).is_absolute():
        raise PlanValidationError(f"{field_name} path must be relative to {root_name}")
    return _resolved_under(root / declared, root, field_name, root_name)


def _require_exact_fields(
    value: Mapping[str, object], expected: frozenset[str], context: str
) -> None:
    if any(not isinstance(key, str) for key in value):
        raise PlanValidationError(f"{context} keys must be strings")
    actual = frozenset(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise PlanValidationError(f"{context} is missing fields: {', '.join(missing)}")
    if unknown:
        raise PlanValidationError(f"{context} has unknown fields: {', '.join(unknown)}")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PlanValidationError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _parse_string_array(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PlanValidationError(f"{field_name} must be a JSON string array")
    parsed = tuple(_require_nonempty_string(item, field_name) for item in value)
    if len(parsed) != len(set(parsed)):
        raise PlanValidationError(f"{field_name} values must be unique")
    return parsed


def _parse_paths(value: object, task_root: Path, field_name: str) -> tuple[Path, ...]:
    if not isinstance(value, list):
        raise PlanValidationError(f"{field_name} must be a JSON string array")
    paths = tuple(
        _resolve_declared_path(
            item,
            root=task_root,
            field_name=f"{field_name}[{index}]",
            root_name="task root",
        )
        for index, item in enumerate(value)
    )
    if len(paths) != len(set(paths)):
        raise PlanValidationError(f"{field_name} paths must be unique")
    return paths


def _parse_argv(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise PlanValidationError("argv must be a nonempty JSON string array")
    if any(not isinstance(argument, str) for argument in value):
        raise PlanValidationError("argv must be a nonempty JSON string array")
    if not value[0].strip():
        raise PlanValidationError("argv[0] executable must be a nonempty literal string")
    if any("\x00" in argument for argument in value):
        raise PlanValidationError("argv arguments must not contain NUL bytes")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class StagePlan:
    """One ordered, argv-only execution stage in a Fast Path plan."""

    execution_stage_id: str
    framework_stage_id: str
    argv: tuple[str, ...]
    inputs: tuple[Path, ...]
    outputs: tuple[Path, ...]
    required_gates: tuple[str, ...]
    stop_gate: str | None
    timeout_seconds: float
    cache: bool

    def __post_init__(self) -> None:
        _require_nonempty_string(self.execution_stage_id, "execution_stage_id")
        if self.framework_stage_id not in FRAMEWORK_STAGE_IDS:
            allowed = ", ".join(sorted(FRAMEWORK_STAGE_IDS))
            raise PlanValidationError(
                f"framework_stage_id must be one of: {allowed}"
            )
        if not isinstance(self.argv, tuple) or not self.argv:
            raise PlanValidationError("argv must be a nonempty immutable string tuple")
        if any(not isinstance(argument, str) or "\x00" in argument for argument in self.argv):
            raise PlanValidationError("argv must contain only strings without NUL bytes")
        if not self.argv[0].strip():
            raise PlanValidationError("argv[0] executable must be a nonempty literal string")
        for field_name, paths in (("inputs", self.inputs), ("outputs", self.outputs)):
            if not isinstance(paths, tuple) or any(not isinstance(path, Path) for path in paths):
                raise PlanValidationError(f"{field_name} must be an immutable path tuple")
        if not isinstance(self.required_gates, tuple):
            raise PlanValidationError("required_gates must be an immutable string tuple")
        for gate in self.required_gates:
            _require_nonempty_string(gate, "required_gates")
            if gate not in CANONICAL_GATE_IDS:
                raise PlanValidationError(f"required_gates contains unknown gate: {gate}")
        if len(self.required_gates) != len(set(self.required_gates)):
            raise PlanValidationError("required_gates values must be unique")
        if self.stop_gate is not None:
            _require_nonempty_string(self.stop_gate, "stop_gate")
            if self.stop_gate not in CANONICAL_GATE_IDS:
                raise PlanValidationError(f"stop_gate is not canonical: {self.stop_gate}")
        _require_positive_finite_number(self.timeout_seconds, "timeout_seconds")
        if not isinstance(self.cache, bool):
            raise PlanValidationError("cache must be a boolean")


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """A validated plan rooted in one trusted workspace and task directory."""

    workspace_root: Path
    task_root: Path
    execution_mode: str
    stages: tuple[StagePlan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_root, Path) or not isinstance(self.task_root, Path):
            raise PlanValidationError("workspace_root and task_root must be paths")
        workspace_root = self.workspace_root.resolve(strict=False)
        task_root = _resolved_under(
            self.task_root,
            workspace_root,
            "task_root",
            "workspace root",
        )
        if workspace_root != self.workspace_root or task_root != self.task_root:
            raise PlanValidationError("workspace_root and task_root must be resolved paths")
        if self.execution_mode != EXECUTION_MODE:
            raise PlanValidationError(
                f"execution_mode must be exactly {EXECUTION_MODE!r}"
            )
        if not isinstance(self.stages, tuple) or not self.stages:
            raise PlanValidationError("stages must be a nonempty immutable stage tuple")
        if any(not isinstance(stage, StagePlan) for stage in self.stages):
            raise PlanValidationError("stages must contain only StagePlan values")
        execution_stage_ids = [stage.execution_stage_id for stage in self.stages]
        if len(execution_stage_ids) != len(set(execution_stage_ids)):
            raise PlanValidationError("execution_stage_id values must be unique")
        stage_ranks = {name: index for index, name in enumerate(FRAMEWORK_STAGE_ORDER)}
        gate_ranks = {name: index for index, name in enumerate(CANONICAL_GATE_ORDER)}
        previous_stage_rank = -1
        previous_stop_rank = -1
        prior_stop_gates: set[str] = set()
        for stage in self.stages:
            for path in (*stage.inputs, *stage.outputs):
                _resolved_under(path, task_root, "stage", "task root")
            for output in stage.outputs:
                relative = output.relative_to(task_root).as_posix()
                if relative in _RESERVED_TASK_OUTPUTS:
                    raise PlanValidationError(
                        f"stage output is reserved for Fast Path state: {relative}"
                    )

            stage_rank = stage_ranks[stage.framework_stage_id]
            if stage_rank < previous_stage_rank:
                raise PlanValidationError("framework stage order cannot move backward")
            previous_stage_rank = stage_rank

            required = set(stage.required_gates)
            missing_entry = _FRAMEWORK_ENTRY_GATES[stage.framework_stage_id] - required
            if missing_entry:
                raise PlanValidationError(
                    "required_gates is missing framework gate prerequisites: "
                    + ", ".join(sorted(missing_entry))
                )
            missing_prior = prior_stop_gates - required
            if missing_prior:
                raise PlanValidationError(
                    "required_gates must include prior stop gates: "
                    + ", ".join(sorted(missing_prior))
                )

            if stage.stop_gate is not None:
                stop_rank = gate_ranks[stage.stop_gate]
                if stop_rank <= previous_stop_rank:
                    raise PlanValidationError("stop gate order must move forward")
                if previous_stop_rank < 0 and stop_rank != 0:
                    raise PlanValidationError("the first stop gate must be gate1")
                if previous_stop_rank >= 0 and stop_rank > previous_stop_rank + 1:
                    raise PlanValidationError(
                        "stop gate sequence cannot skip an intermediate gate"
                    )
                previous_stop_rank = stop_rank
                prior_stop_gates.add(stage.stop_gate)

    @classmethod
    def from_object(
        cls,
        value: Mapping[str, object],
        *,
        workspace_root: str | Path,
    ) -> Self:
        """Parse a JSON-compatible mapping under a trusted workspace root."""

        if not isinstance(value, Mapping):
            raise PlanValidationError("plan must be a JSON object")
        _require_exact_fields(value, _PLAN_FIELDS, "plan")

        resolved_workspace = Path(workspace_root).resolve(strict=False)
        if not resolved_workspace.is_dir():
            raise PlanValidationError("workspace_root must be an existing directory")
        task_root = _resolve_declared_path(
            value["task_root"],
            root=resolved_workspace,
            field_name="task_root",
            root_name="workspace root",
        )
        execution_mode = _require_nonempty_string(
            value["execution_mode"], "execution_mode"
        )
        if execution_mode != EXECUTION_MODE:
            raise PlanValidationError(
                f"execution_mode must be exactly {EXECUTION_MODE!r}"
            )

        stage_values = value["stages"]
        if not isinstance(stage_values, list) or not stage_values:
            raise PlanValidationError("stages must be a nonempty JSON array")
        stages = tuple(
            cls._parse_stage(stage, task_root=task_root, index=index)
            for index, stage in enumerate(stage_values)
        )
        return cls(
            workspace_root=resolved_workspace,
            task_root=task_root,
            execution_mode=execution_mode,
            stages=stages,
        )

    @classmethod
    def from_json(
        cls,
        value: str | bytes | bytearray,
        *,
        workspace_root: str | Path,
    ) -> Self:
        """Parse a JSON string or bytes into a validated execution plan."""

        if not isinstance(value, (str, bytes, bytearray)):
            raise PlanValidationError("plan JSON must be text or bytes")
        try:
            decoded = json.loads(value, object_pairs_hook=_reject_duplicate_json_keys)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PlanValidationError(f"plan JSON is invalid: {error}") from error
        if not isinstance(decoded, Mapping):
            raise PlanValidationError("plan JSON must contain an object")
        return cls.from_object(decoded, workspace_root=workspace_root)

    @staticmethod
    def _parse_stage(
        value: object,
        *,
        task_root: Path,
        index: int,
    ) -> StagePlan:
        if not isinstance(value, Mapping):
            raise PlanValidationError(f"stages[{index}] must be a JSON object")
        _require_exact_fields(value, _STAGE_FIELDS, f"stages[{index}]")

        execution_stage_id = _require_nonempty_string(
            value["execution_stage_id"], "execution_stage_id"
        )
        framework_stage_id = _require_nonempty_string(
            value["framework_stage_id"], "framework_stage_id"
        )
        if framework_stage_id not in FRAMEWORK_STAGE_IDS:
            allowed = ", ".join(sorted(FRAMEWORK_STAGE_IDS))
            raise PlanValidationError(
                f"framework_stage_id must be one of: {allowed}"
            )

        stop_gate_value = value["stop_gate"]
        stop_gate = (
            None
            if stop_gate_value is None
            else _require_nonempty_string(stop_gate_value, "stop_gate")
        )
        timeout = _require_positive_finite_number(
            value["timeout_seconds"], "timeout_seconds"
        )
        cache = value["cache"]
        if not isinstance(cache, bool):
            raise PlanValidationError("cache must be a boolean")

        return StagePlan(
            execution_stage_id=execution_stage_id,
            framework_stage_id=framework_stage_id,
            argv=_parse_argv(value["argv"]),
            inputs=_parse_paths(value["inputs"], task_root, "inputs"),
            outputs=_parse_paths(value["outputs"], task_root, "outputs"),
            required_gates=_parse_string_array(value["required_gates"], "required_gates"),
            stop_gate=stop_gate,
            timeout_seconds=timeout,
            cache=cache,
        )

    def stage(self, execution_stage_id: str) -> StagePlan:
        """Return a stage by its unique execution identifier."""

        for stage in self.stages:
            if stage.execution_stage_id == execution_stage_id:
                return stage
        raise PlanValidationError(
            f"unknown execution_stage_id: {execution_stage_id!r}"
        )

    def input_fingerprint(self, execution_stage_id: str) -> str:
        """Hash canonical stage semantics and current input file contents."""

        stage = self.stage(execution_stage_id)
        stage_index = self.stages.index(stage)
        input_records = []
        for input_path in sorted(stage.inputs, key=self._relative_path):
            resolved = _resolved_under(
                input_path,
                self.task_root,
                "input",
                "task root",
            )
            relative_path = self._relative_path(input_path)
            if not resolved.exists():
                input_records.append({"path": relative_path, "state": "missing"})
                continue
            if not resolved.is_file():
                raise PlanValidationError(
                    f"input path must be a regular file: {relative_path}"
                )
            input_records.append(
                {
                    "path": relative_path,
                    "state": "file",
                    "sha256": _sha256_file(resolved),
                }
            )

        implementation_records = []
        declared_inputs = {path.resolve(strict=False) for path in stage.inputs}
        seen_implementations: set[Path] = set()
        implementation_suffixes = {".py", ".pyw", ".js", ".mjs", ".cjs", ".sh"}
        for argument_index, argument in enumerate(stage.argv):
            candidate = Path(argument)
            if argument_index != 0 and candidate.suffix.lower() not in implementation_suffixes:
                continue
            if not candidate.is_absolute():
                candidate = self.task_root / candidate
            try:
                resolved_candidate = candidate.resolve(strict=True)
            except OSError:
                continue
            if (
                resolved_candidate in declared_inputs
                or resolved_candidate in seen_implementations
                or not resolved_candidate.is_file()
            ):
                continue
            seen_implementations.add(resolved_candidate)
            implementation_records.append(
                {
                    "argv": argument,
                    "sha256": _sha256_file(resolved_candidate),
                }
            )

        payload: dict[str, Any] = {
            "execution_mode": self.execution_mode,
            "task_root": self.task_root.relative_to(self.workspace_root).as_posix(),
            "stage_index": stage_index,
            "stage": {
                "execution_stage_id": stage.execution_stage_id,
                "framework_stage_id": stage.framework_stage_id,
                "argv": list(stage.argv),
                "inputs": sorted(self._relative_path(path) for path in stage.inputs),
                "outputs": sorted(self._relative_path(path) for path in stage.outputs),
                "required_gates": sorted(stage.required_gates),
                "stop_gate": stage.stop_gate,
                "timeout_seconds": stage.timeout_seconds,
                "cache": stage.cache,
            },
            "input_files": input_records,
            "implementation_files": implementation_records,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _relative_path(self, path: Path) -> str:
        return path.relative_to(self.task_root).as_posix()


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Stable result envelope returned by commands and stage invocations."""

    status: str
    exit_code: int
    request_id: str
    invocation_id: str
    idempotency_key: str
    state_revision_before: int
    state_revision_after: int
    event_sequence: int
    next_actions: tuple[str, ...]
    error_code: str | None

    def __post_init__(self) -> None:
        _require_nonempty_string(self.status, "status")
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise PlanValidationError("exit_code must be an integer")
        _require_nonempty_string(self.request_id, "request_id")
        _require_nonempty_string(self.invocation_id, "invocation_id")
        _require_nonempty_string(self.idempotency_key, "idempotency_key")
        before = _require_nonnegative_integer(
            self.state_revision_before, "state_revision_before"
        )
        after = _require_nonnegative_integer(
            self.state_revision_after, "state_revision_after"
        )
        if after < before:
            raise PlanValidationError(
                "state_revision_after must not precede state_revision_before"
            )
        _require_nonnegative_integer(self.event_sequence, "event_sequence")
        if not isinstance(self.next_actions, tuple):
            raise PlanValidationError("next_actions must be an immutable string tuple")
        for action in self.next_actions:
            _require_nonempty_string(action, "next_actions")
        if self.error_code is not None:
            _require_nonempty_string(self.error_code, "error_code")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
