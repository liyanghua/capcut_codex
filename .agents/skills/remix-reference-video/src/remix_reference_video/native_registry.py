"""Lock-safe registry and thin execution bridge for native stage adapters.

The registry is intentionally independent from the CLI production lock. It is
usable by isolated fixtures and development runners while ``manifest.json``
continues to control whether ordinary Track B production may start.
"""

from __future__ import annotations

import inspect
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from .adapters import content_fingerprint
from .orchestrator import StageAdapter, creative_dag, dag_for_task, default_dag
from .stage_input_validator import StageInputValidator
from .storage import StorageError, atomic_write_json, read_json_object


class NativeRegistryError(StorageError):
    """Raised when a native adapter registry violates the production DAG."""


class NativeStageAdapter:
    """Adapt a pure stage function to the Runner's StageAdapter contract."""

    def __init__(
        self,
        task_root: Path,
        *,
        execution_stage_id: str,
        implementation_version: str,
        required_inputs: tuple[Path, ...],
        declared_outputs: tuple[Path, ...],
        execute_fn: Callable[..., Mapping[str, object]],
        stop_gate: str | None = None,
        require_stage_input: bool = False,
        domain_managed_outputs: bool = False,
    ) -> None:
        self.task_root = Path(task_root).resolve(strict=True)
        self.execution_stage_id = execution_stage_id
        self.implementation_version = implementation_version
        self._inputs = tuple(Path(path).resolve(strict=False) for path in required_inputs)
        self._outputs = tuple(Path(path).resolve(strict=False) for path in declared_outputs)
        self._execute_fn = execute_fn
        self.stop_gate = stop_gate
        self.require_stage_input = require_stage_input
        self.domain_managed_outputs = domain_managed_outputs
        if not execution_stage_id or not implementation_version:
            raise NativeRegistryError("native adapter identity is required")
        if not callable(execute_fn):
            raise NativeRegistryError("native adapter execute_fn must be callable")
        for path in (*self._inputs, *self._outputs):
            resolved = path.resolve(strict=False)
            if not self._inside(resolved):
                raise NativeRegistryError(f"adapter path escapes task root: {path}")

    def required_inputs(self) -> tuple[Path, ...]:
        return self._inputs

    def required_gates(self) -> tuple[str, ...]:
        return ()

    def declared_outputs(self) -> tuple[Path, ...]:
        return self._outputs

    def cache_fingerprint(self) -> str:
        handoff = self.task_root / "stage_inputs" / f"{self.execution_stage_id}.json"
        inputs = self._inputs + ((handoff,) if handoff.exists() or handoff.is_symlink() else ())
        return content_fingerprint(
            self.execution_stage_id, self.implementation_version, inputs
        )

    def execute(self, *, attempt_id: str) -> dict[str, object]:
        if not attempt_id:
            raise NativeRegistryError("attempt_id is required")
        handoff = self.task_root / "stage_inputs" / f"{self.execution_stage_id}.json"
        payload: Mapping[str, object] = {}
        if self.require_stage_input and not handoff.is_file():
            raise NativeRegistryError(f"stage input is required: {handoff.name}")
        if handoff.exists() or handoff.is_symlink():
            result = StageInputValidator(self.task_root).validate(
                handoff, expected_stage_id=self.execution_stage_id
            )
            if not result.valid:
                raise NativeRegistryError("invalid stage input: " + "; ".join(result.errors))
            raw = json.loads(handoff.read_text(encoding="utf-8"))
            payload = raw["payload"]
        output = self._call(payload)
        if not isinstance(output, Mapping):
            raise NativeRegistryError("native stage function must return an object")
        if self.domain_managed_outputs:
            missing = [path for path in self._outputs if not path.is_file() or path.is_symlink()]
            if missing:
                raise NativeRegistryError(f"domain adapter did not produce: {missing[0].name}")
            return {"status": "succeeded", "attempt_id": attempt_id, **dict(output)}
        if len(self._outputs) == 1:
            writes = [(self._outputs[0], output)]
        else:
            writes = []
            for destination in self._outputs:
                key = destination.stem if destination.suffix == ".json" else destination.name.replace(".", "_")
                value = output.get(key)
                if not isinstance(value, (Mapping, str)):
                    raise NativeRegistryError(
                        f"native stage output must provide content for {key}"
                    )
                writes.append((destination, value))
        for destination, value in writes:
            if destination.is_symlink() or not self._inside(destination.resolve(strict=False)):
                raise NativeRegistryError(f"unsafe native adapter output: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(value, str):
                self._atomic_write_text(destination, value)
            else:
                atomic_write_json(destination, dict(value))
        return {"status": "succeeded", "attempt_id": attempt_id}

    def _call(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        try:
            parameters = inspect.signature(self._execute_fn).parameters
        except (TypeError, ValueError):
            parameters = {"payload": None}
        if parameters:
            return self._execute_fn(payload)
        return self._execute_fn()

    def _inside(self, path: Path) -> bool:
        return path == self.task_root or self.task_root in path.parents

    @staticmethod
    def _atomic_write_text(path: Path, value: str) -> None:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


class NativeAdapterRegistry:
    """Register native adapters against the normative production DAG."""

    def __init__(self, task_root: Path) -> None:
        self.task_root = Path(task_root).resolve(strict=True)
        # Registration accepts the union of known generations. Execution order
        # and exposure still follow the task-selected frozen DAG.
        self._nodes = {node.node_id: node for node in (*default_dag(), *creative_dag())}
        self._adapters: dict[str, StageAdapter] = {}

    def _selected_dag(self) -> tuple[object, ...]:
        # Empty roots are used by adapter-registration fixtures before a task
        # is initialized. Initialized tasks must follow their frozen DAG.
        state = self.task_root / "pipeline_state.json"
        marker = self.task_root / "g_b_frozen_input_snapshot.json"
        baseline = self.task_root / "content_baseline.json"
        if marker.is_file() or (baseline.is_file() and "narrative_contract_version" in _read_json_keys(baseline)):
            return dag_for_task(self.task_root)
        if state.is_file() and "production_dag_version" in _read_json_keys(state):
            return dag_for_task(self.task_root)
        return default_dag()

    def register(self, adapter: StageAdapter) -> None:
        stage_id = getattr(adapter, "execution_stage_id", None)
        if not isinstance(stage_id, str) or stage_id not in self._nodes:
            raise NativeRegistryError(f"adapter is not a node in the production DAG: {stage_id}")
        if stage_id in self._adapters:
            raise NativeRegistryError(f"duplicate native adapter: {stage_id}")
        if not callable(getattr(adapter, "execute", None)):
            raise NativeRegistryError(f"adapter has no execute method: {stage_id}")
        self._adapters[stage_id] = adapter

    def get(self, stage_id: str) -> StageAdapter:
        try:
            return self._adapters[stage_id]
        except KeyError as error:
            raise NativeRegistryError(f"native adapter is not registered: {stage_id}") from error

    def stage_ids(self) -> tuple[str, ...]:
        return tuple(node.node_id for node in self._selected_dag() if node.node_id in self._adapters)

    def adapters(self) -> tuple[StageAdapter, ...]:
        return tuple(self._adapters[stage_id] for stage_id in self.stage_ids())


__all__ = ["NativeAdapterRegistry", "NativeRegistryError", "NativeStageAdapter"]


def _read_json_keys(path: Path) -> Mapping[str, object]:
    try:
        value = read_json_object(path)
    except (OSError, StorageError):
        return {}
    return value
