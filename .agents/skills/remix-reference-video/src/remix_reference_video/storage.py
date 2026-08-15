"""Durable task-local state, event, and metric storage."""

from __future__ import annotations

import copy
import errno
import fcntl
import json
import os
import tempfile
import threading
import uuid
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


class StorageError(RuntimeError):
    """Raised when durable Fast Path state is invalid or cannot be reconciled."""


class RevisionConflict(StorageError):
    """Raised when a writer uses a stale expected state revision."""


class TaskBusy(StorageError):
    """Raised when another invocation already owns the task execution lock."""


def _open_nofollow(path: Path, flags: int, mode: int = 0o600) -> int:
    """Open a control file without following a final-component symlink."""

    if path.is_symlink():
        raise StorageError(f"control path must not be a symlink: {path}")
    try:
        return os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise StorageError(f"control path must not be a symlink: {path}") from error
        raise


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def atomic_write_json(path: Path, value: object) -> None:
    """Write JSON through a same-directory staging file and atomic replace."""

    path = Path(path)
    if path.is_symlink():
        raise StorageError(f"control path must not be a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_bytes(value)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise StorageError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _decode_json_object(value: str | bytes, context: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value, object_pairs_hook=_reject_duplicate_json_keys)
    except StorageError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        detail = getattr(error, "msg", str(error))
        raise StorageError(f"invalid JSON in {context}: {detail}") from error
    if not isinstance(decoded, dict):
        raise StorageError(f"JSON root must be an object: {context}")
    return decoded


def read_json_object(path: Path) -> dict[str, Any]:
    """Read one strict JSON object without creating task-local files."""

    try:
        descriptor = _open_nofollow(Path(path), os.O_RDONLY)
    except FileNotFoundError as error:
        raise StorageError(f"required state file is missing: {path}") from error
    with os.fdopen(descriptor, "rb") as stream:
        value = stream.read()
    return _decode_json_object(value, str(path))


def read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    """Read strict JSON object records without creating task-local files."""

    try:
        descriptor = _open_nofollow(Path(path), os.O_RDONLY)
    except FileNotFoundError:
        return []
    records: list[dict[str, Any]] = []
    with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = _decode_json_object(line, f"{path} at line {line_number}")
            records.append(value)
    return records


def _last_jsonl_record(path: Path) -> dict[str, Any] | None:
    """Read only the final nonempty JSONL line."""

    try:
        descriptor = _open_nofollow(Path(path), os.O_RDONLY)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as stream:
        position = stream.seek(0, os.SEEK_END)
        if position == 0:
            return None
        buffer = b""
        while position > 0:
            chunk_size = min(4096, position)
            position -= chunk_size
            stream.seek(position)
            buffer = stream.read(chunk_size) + buffer
            lines = buffer.splitlines()
            if position == 0 or len(lines) >= 2:
                for line in reversed(lines):
                    if line.strip():
                        return _decode_json_object(line, f"final record in {path}")
        return None


class TaskStorage:
    """Serialize state and append-only records with one task-local file lock."""

    def __init__(self, task_root: Path) -> None:
        requested_root = Path(task_root)
        if requested_root.is_symlink():
            raise StorageError(f"task root must not be a symlink: {requested_root}")
        self.task_root = requested_root.resolve(strict=True)
        if not self.task_root.is_dir():
            raise StorageError(f"task root must be a directory: {requested_root}")
        root_stat = self.task_root.stat()
        self._task_root_identity = (root_stat.st_dev, root_stat.st_ino)
        self.state_path = self.task_root / "pipeline_state.json"
        self.events_path = self.task_root / "pipeline_events.jsonl"
        self.metrics_path = self.task_root / "stage_metrics.jsonl"
        self.lock_path = self.task_root / ".fast_path.lock"
        for path in (
            self.state_path,
            self.events_path,
            self.metrics_path,
            self.lock_path,
        ):
            if path.is_symlink():
                raise StorageError(f"control path must not be a symlink: {path}")
        self._invocation_lock_owner: int | None = None

    def _assert_task_root_stable(self) -> None:
        if self.task_root.is_symlink():
            raise StorageError(f"task root must not be a symlink: {self.task_root}")
        try:
            root_stat = self.task_root.stat()
        except OSError as error:
            raise StorageError(f"task root is unavailable: {self.task_root}") from error
        if (root_stat.st_dev, root_stat.st_ino) != self._task_root_identity:
            raise StorageError(f"task root identity changed: {self.task_root}")

    @contextmanager
    def invocation_lock(self) -> Iterator[None]:
        """Hold the task lock for one complete non-reentrant invocation."""

        if self._invocation_lock_owner is not None:
            raise StorageError("task invocation lock is not reentrant")
        self._assert_task_root_stable()
        descriptor = _open_nofollow(
            self.lock_path, os.O_RDWR | os.O_CREAT
        )
        with os.fdopen(descriptor, "a+b") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise TaskBusy("task execution is already in progress") from error
            self._invocation_lock_owner = threading.get_ident()
            try:
                yield
            finally:
                self._invocation_lock_owner = None
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _locked(self, operation: int = fcntl.LOCK_EX) -> Iterator[None]:
        if self._invocation_lock_owner == threading.get_ident():
            self._assert_task_root_stable()
            yield
            return
        self._assert_task_root_stable()
        descriptor = _open_nofollow(
            self.lock_path, os.O_RDWR | os.O_CREAT
        )
        with os.fdopen(descriptor, "a+b") as lock:
            fcntl.flock(lock.fileno(), operation)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def initialize_state(self, state: Mapping[str, object]) -> dict[str, Any]:
        initial = dict(state)
        if initial.get("state_revision") != 0:
            raise StorageError("initial state_revision must be 0")
        with self._locked():
            if self.state_path.exists():
                raise StorageError(f"state already exists: {self.state_path}")
            atomic_write_json(self.state_path, initial)
        return copy.deepcopy(initial)

    def read_state(self) -> dict[str, Any]:
        with self._locked(fcntl.LOCK_SH):
            return read_json_object(self.state_path)

    def update_state(
        self,
        transform: Callable[[dict[str, Any]], Mapping[str, object]],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        with self._locked():
            current = read_json_object(self.state_path)
            current_revision = current.get("state_revision")
            if (
                isinstance(current_revision, bool)
                or not isinstance(current_revision, int)
                or current_revision < 0
            ):
                raise StorageError("state_revision must be a nonnegative integer")
            if expected_revision is not None and expected_revision != current_revision:
                raise RevisionConflict(
                    f"expected state revision {expected_revision}, found {current_revision}"
                )
            changed = transform(copy.deepcopy(current))
            if not isinstance(changed, Mapping):
                raise StorageError("state transform must return a mapping")
            updated = dict(changed)
            updated["state_revision"] = current_revision + 1
            atomic_write_json(self.state_path, updated)
            return copy.deepcopy(updated)

    def append_event(
        self, event: Mapping[str, object], *, state_revision: int
    ) -> dict[str, Any]:
        if (
            isinstance(state_revision, bool)
            or not isinstance(state_revision, int)
            or state_revision < 0
        ):
            raise StorageError("event state_revision must be a nonnegative integer")
        with self._locked():
            return self._append_event_locked(event, state_revision=state_revision)

    def _append_event_locked(
        self, event: Mapping[str, object], *, state_revision: int
    ) -> dict[str, Any]:
        reserved = {"event_id", "sequence", "occurred_at", "state_revision"}
        overlap = reserved.intersection(event)
        if overlap:
            raise StorageError(f"event cannot override reserved fields: {sorted(overlap)}")
        last = _last_jsonl_record(self.events_path)
        last_sequence = 0 if last is None else last.get("sequence")
        if isinstance(last_sequence, bool) or not isinstance(last_sequence, int):
            raise StorageError("last event sequence must be an integer")
        record = {
            **dict(event),
            "event_id": str(uuid.uuid4()),
            "sequence": last_sequence + 1,
            "occurred_at": _utc_now(),
            "state_revision": state_revision,
        }
        self._append_jsonl_locked(self.events_path, record)
        return record

    def append_metric(self, metric: Mapping[str, object]) -> dict[str, Any]:
        if "recorded_at" in metric:
            raise StorageError("metric cannot override recorded_at")
        record = {**dict(metric), "recorded_at": _utc_now()}
        with self._locked():
            self._append_jsonl_locked(self.metrics_path, record)
        return record

    @staticmethod
    def _append_jsonl_locked(path: Path, record: Mapping[str, object]) -> None:
        payload = (
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        descriptor = _open_nofollow(
            path, os.O_WRONLY | os.O_APPEND | os.O_CREAT
        )
        with os.fdopen(descriptor, "ab") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    def read_events(self) -> list[dict[str, Any]]:
        with self._locked(fcntl.LOCK_SH):
            return read_jsonl_records(self.events_path)

    def read_metrics(self) -> list[dict[str, Any]]:
        with self._locked(fcntl.LOCK_SH):
            return read_jsonl_records(self.metrics_path)

    def reconcile_event_gap(self) -> dict[str, Any] | None:
        """Append an audit marker when durable state is newer than its event log."""

        with self._locked():
            state = read_json_object(self.state_path)
            state_revision = state.get("state_revision")
            if (
                isinstance(state_revision, bool)
                or not isinstance(state_revision, int)
                or state_revision < 0
            ):
                raise StorageError("state_revision must be a nonnegative integer")
            events = read_jsonl_records(self.events_path)
            event_revisions = [event.get("state_revision") for event in events]
            if any(
                isinstance(revision, bool) or not isinstance(revision, int)
                for revision in event_revisions
            ):
                raise StorageError("event state_revision values must be integers")
            last_event_revision = max(event_revisions, default=0)
            if last_event_revision > state_revision:
                raise StorageError("event log is ahead of authoritative state")
            if last_event_revision == state_revision:
                return None
            return self._append_event_locked(
                {
                    "event_type": "state.reconciled",
                    "from_state_revision": last_event_revision,
                    "to_state_revision": state_revision,
                },
                state_revision=state_revision,
            )
