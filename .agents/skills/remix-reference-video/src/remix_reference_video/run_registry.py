"""Explicit, revisioned run-id to task-root registry for the local workbench."""

from __future__ import annotations

import fcntl
import hashlib
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .production_runtime import ProductionRuntimeConfig
from .storage import StorageError, atomic_write_json, read_json_object


class RunRegistryError(StorageError):
    pass


class RunRegistry:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace = Path(workspace_root).resolve(strict=True)
        if not self.workspace.is_dir(): raise RunRegistryError("workspace root must be a directory")
        directory = self.workspace / "workbench"; directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "run_registry.json"; self.lock_path = directory / ".run_registry.lock"
        if self.path.is_symlink() or self.lock_path.is_symlink(): raise RunRegistryError("registry paths must not be symlinks")

    def register(self, task_dir: Path) -> dict[str, Any]:
        task, state, frozen, frozen_hash, runtime_hash = self._validate_task(task_dir)
        run_id = str(state["run_id"])
        with self._lock():
            registry = self._read()
            if run_id in registry["runs"]: raise RunRegistryError(f"run already registered: {run_id}")
            revision = int(registry["registry_revision"]) + 1; now = self._now()
            entry = {"run_id":run_id,"task_dir":str(task),"execution_mode":state["execution_mode"],"pair_role":frozen["pair_role"],"g_b_frozen_input_snapshot_sha256":frozen_hash,"production_runtime_config_sha256":runtime_hash,"created_at":now,"updated_at":now,"status":"active","registry_revision":revision,"audit_history":[{"action":"register","actor":"system","occurred_at":now}]}
            registry["runs"][run_id] = entry; registry["registry_revision"] = revision
            atomic_write_json(self.path, registry)
            return dict(entry)

    def ensure_registered(self, task_dir: Path) -> dict[str, Any]:
        """Register a G-B side once, or validate and return its current entry."""

        task, state, frozen, frozen_hash, runtime_hash = self._validate_task(task_dir)
        run_id = str(state["run_id"])
        with self._lock():
            registry = self._read()
            existing = registry["runs"].get(run_id)
            if isinstance(existing, dict):
                if (
                    existing.get("task_dir") != str(task)
                    or existing.get("pair_role") != frozen.get("pair_role")
                    or existing.get("g_b_frozen_input_snapshot_sha256") != frozen_hash
                    or existing.get("production_runtime_config_sha256") != runtime_hash
                ):
                    raise RunRegistryError("run registry is stale")
                return dict(existing)
            revision = int(registry["registry_revision"]) + 1
            now = self._now()
            entry = {
                "run_id": run_id,
                "task_dir": str(task),
                "execution_mode": state["execution_mode"],
                "pair_role": frozen["pair_role"],
                "g_b_frozen_input_snapshot_sha256": frozen_hash,
                "production_runtime_config_sha256": runtime_hash,
                "created_at": now,
                "updated_at": now,
                "status": "active",
                "registry_revision": revision,
                "audit_history": [
                    {"action": "register", "actor": "gb-pair", "occurred_at": now}
                ],
            }
            registry["runs"][run_id] = entry
            registry["registry_revision"] = revision
            atomic_write_json(self.path, registry)
            return dict(entry)

    def repair(self, run_id: str, task_dir: Path, *, expected_registry_revision: int, actor: str) -> dict[str, Any]:
        if not actor.strip(): raise RunRegistryError("repair actor is required")
        task, state, frozen, frozen_hash, runtime_hash = self._validate_task(task_dir)
        if state.get("run_id") != run_id: raise RunRegistryError("repair run_id mismatch")
        with self._lock():
            registry = self._read(); current = int(registry["registry_revision"])
            if current != expected_registry_revision: raise RunRegistryError("registry revision conflict")
            previous = registry["runs"].get(run_id)
            if not isinstance(previous, dict): raise RunRegistryError("run is not registered")
            revision = current + 1; now = self._now()
            entry = {**previous,"task_dir":str(task),"pair_role":frozen["pair_role"],"g_b_frozen_input_snapshot_sha256":frozen_hash,"production_runtime_config_sha256":runtime_hash,"updated_at":now,"registry_revision":revision,"audit_history":[*previous.get("audit_history",[]),{"action":"repair","actor":actor.strip(),"occurred_at":now,"previous_task_dir":previous.get("task_dir")} ]}
            registry["runs"][run_id] = entry; registry["registry_revision"] = revision
            atomic_write_json(self.path, registry); return dict(entry)

    def resolve(self, run_id: str) -> Path:
        registry = self._read(); entry = registry["runs"].get(run_id)
        if not isinstance(entry, dict): raise RunRegistryError("run is not registered")
        task, state, frozen, frozen_hash, runtime_hash = self._validate_task(Path(str(entry.get("task_dir"))))
        if state.get("run_id") != run_id or frozen_hash != entry.get("g_b_frozen_input_snapshot_sha256") or runtime_hash != entry.get("production_runtime_config_sha256") or frozen.get("pair_role") != entry.get("pair_role"):
            raise RunRegistryError("run registry is stale")
        return task

    def get(self, run_id: str) -> dict[str, Any]:
        self.resolve(run_id); entry = self._read()["runs"].get(run_id)
        return dict(entry)

    def _validate_task(self, task_dir: Path) -> tuple[Path, dict[str, Any], dict[str, Any], str, str]:
        requested = Path(task_dir)
        if requested.is_symlink(): raise RunRegistryError("task path must not be a symlink")
        task = requested.resolve(strict=True)
        if task != self.workspace and self.workspace not in task.parents: raise RunRegistryError("task path escapes workspace")
        if not task.is_dir(): raise RunRegistryError("task path must be a directory")
        state = read_json_object(task / "pipeline_state.json")
        if state.get("execution_mode") != "track-b-production" or not isinstance(state.get("run_id"), str): raise RunRegistryError("task is not a Track-B run")
        frozen_path = task / "g_b_frozen_input_snapshot.json"
        if frozen_path.is_symlink() or not frozen_path.is_file(): raise RunRegistryError("frozen input snapshot is required")
        frozen = read_json_object(frozen_path)
        if frozen.get("artifact_type") != "g_b_frozen_input_snapshot" or frozen.get("pair_role") not in {"cold","hot"}: raise RunRegistryError("frozen input snapshot is invalid")
        required_hashes = ("reference_sha256", "brief_sha256", "asset_profiles_sha256")
        if any(not self._is_sha256(frozen.get(name)) for name in required_hashes):
            raise RunRegistryError("frozen input snapshot contract is incomplete")
        if frozen.get("approval_records") != []:
            raise RunRegistryError("frozen input snapshot approval records must be empty")
        asset_snapshot = frozen.get("asset_snapshot")
        if not isinstance(asset_snapshot, dict) or not asset_snapshot:
            raise RunRegistryError("frozen input snapshot asset source contract is required")
        for name, digest in asset_snapshot.items():
            if not isinstance(name, str) or Path(name).name != name or not self._is_sha256(digest):
                raise RunRegistryError("frozen input snapshot asset source contract is invalid")

        references = sorted(task.glob("reference-*.mp4"))
        if len(references) != 1 or references[0].is_symlink() or not references[0].is_file():
            raise RunRegistryError("frozen input snapshot requires one local reference")
        brief = task / "project_brief.json"
        profiles = task / "asset_profiles.json"
        for path, expected, label in (
            (references[0], frozen["reference_sha256"], "reference"),
            (brief, frozen["brief_sha256"], "brief"),
            (profiles, frozen["asset_profiles_sha256"], "asset profiles"),
        ):
            if path.is_symlink() or not path.is_file() or self._sha256(path) != expected:
                raise RunRegistryError(f"frozen input snapshot {label} hash mismatch")

        runtime_path = task / "production_runtime_config.json"
        if runtime_path.is_symlink() or not runtime_path.is_file():
            raise RunRegistryError("production runtime config is required for a registered G-B run")
        try:
            runtime = ProductionRuntimeConfig.from_file(runtime_path)
        except (OSError, ValueError) as error:
            raise RunRegistryError(f"production runtime config is invalid: {error}") from error
        if runtime.archive_root is not None:
            raise RunRegistryError("registered G-B runs must keep archive disabled")
        if runtime.reference_path != references[0] or runtime.brief_path != brief or runtime.asset_profiles_path != profiles:
            raise RunRegistryError("production runtime config does not bind the frozen inputs")
        for name, expected in asset_snapshot.items():
            source = runtime.asset_root / str(name)
            if source.is_symlink() or not source.is_file() or self._sha256(source) != expected:
                raise RunRegistryError(f"frozen asset source hash mismatch: {name}")

        frozen_hash = self._sha256(frozen_path)
        runtime_hash = self._sha256(runtime_path)
        return task, state, frozen, frozen_hash, runtime_hash

    def _read(self) -> dict[str, Any]:
        if not self.path.exists(): return {"registry_revision":0,"runs":{}}
        if self.path.is_symlink(): raise RunRegistryError("registry must not be a symlink")
        value = read_json_object(self.path)
        if not isinstance(value.get("registry_revision"), int) or not isinstance(value.get("runs"), dict): raise RunRegistryError("run registry is invalid")
        return value

    @contextmanager
    def _lock(self) -> Iterator[None]:
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _now() -> str: return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @staticmethod
    def _is_sha256(value: object) -> bool:
        return isinstance(value, str) and len(value) == 64 and all(
            character in "0123456789abcdef" for character in value
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
