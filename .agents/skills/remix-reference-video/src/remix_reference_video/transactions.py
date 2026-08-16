"""Recoverable task-local commit protocol for Track B state changes."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .artifact_validator import ArtifactValidator
from .storage import (
    RevisionConflict,
    StorageError,
    TaskStorage,
    atomic_write_json,
    read_json_object,
)

_TRANSACTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True, slots=True)
class ArtifactPromotion:
    staged_path: Path
    final_path: Path
    expected_type: str | None = None


class TransactionManager:
    """Prepare, commit, and reconcile one task's durable mutations."""

    def __init__(self, storage: TaskStorage) -> None:
        self.storage = storage
        self.root = storage.task_root
        self.transactions_dir = self.root / ".transactions"

    def prepare(
        self,
        *,
        transaction_id: str,
        expected_revision: int,
        state_changes: Mapping[str, object],
        event: Mapping[str, object],
        metric: Mapping[str, object] | None = None,
        promotions: tuple[ArtifactPromotion, ...] = (),
    ) -> dict[str, Any]:
        self._validate_id(transaction_id)
        if not isinstance(state_changes, Mapping) or not isinstance(event, Mapping):
            raise StorageError("state_changes and event must be mappings")
        with self.storage.invocation_lock():
            state = self.storage.read_state()
            revision = self._revision(state)
            if revision != expected_revision:
                raise RevisionConflict(
                    f"expected state revision {expected_revision}, found {revision}"
                )
            path = self._record_path(transaction_id)
            if path.exists():
                existing = read_json_object(path)
                if existing.get("status") in {"prepared", "committed"}:
                    return existing
                raise StorageError(f"transaction id is not reusable: {transaction_id}")
            promotion_records = [self._promotion_record(item) for item in promotions]
            record: dict[str, Any] = {
                "transaction_id": transaction_id,
                "status": "prepared",
                "state_revision_before": revision,
                "state_revision_after": revision + 1,
                "state_changes": dict(state_changes),
                "event": dict(event),
                "metric": None if metric is None else dict(metric),
                "promotions": promotion_records,
            }
            atomic_write_json(path, record)
            return record

    def commit(self, transaction_id: str) -> dict[str, Any]:
        self._validate_id(transaction_id)
        with self.storage.invocation_lock():
            record = self._read_record(transaction_id)
            if record.get("status") == "committed":
                return record
            if record.get("status") != "prepared":
                raise StorageError(f"transaction is not prepared: {transaction_id}")
            state = self.storage.read_state()
            before = record["state_revision_before"]
            if self._revision(state) != before:
                raise RevisionConflict(
                    f"expected state revision {before}, found {self._revision(state)}"
                )
            self._validate_promotions(record)
            self._promote(record)
            updated = self.storage.update_state(
                lambda current: current | dict(record["state_changes"]),
                expected_revision=before,
            )
            self._append_event_once(record, updated["state_revision"])
            self._append_metric_once(record, partial=False)
            record["status"] = "committed"
            atomic_write_json(self._record_path(transaction_id), record)
            return record

    def reconcile(self, transaction_id: str) -> dict[str, Any]:
        self._validate_id(transaction_id)
        with self.storage.invocation_lock():
            record = self._read_record(transaction_id)
            if record.get("status") in {"rolled_back", "blocked"}:
                return record
            state = self.storage.read_state()
            revision = self._revision(state)
            before = record["state_revision_before"]
            after = record["state_revision_after"]
            if revision == before:
                self._remove_promoted_artifacts(record)
                record["status"] = "rolled_back"
                record["orphan_cleanup"] = "completed"
            elif revision == after:
                self._append_event_once(record, after)
                self._append_metric_once(record, partial=True)
                record["status"] = "committed"
            else:
                blocker = {
                    "category": "transaction_revision_conflict",
                    "transaction_id": transaction_id,
                    "expected": [before, after],
                    "actual": revision,
                }
                self.storage.update_state(
                    lambda current: current
                    | {"blockers": [*current.get("blockers", []), blocker]},
                    expected_revision=revision,
                )
                record["status"] = "blocked"
                record["blocking_reason"] = blocker
            atomic_write_json(self._record_path(transaction_id), record)
            return record

    def _promotion_record(self, promotion: ArtifactPromotion) -> dict[str, str | None]:
        staged = self._task_path(promotion.staged_path, "staged_path", must_exist=True)
        final = self._task_path(promotion.final_path, "final_path", must_exist=False)
        if not staged.is_file() or staged.is_symlink():
            raise StorageError("staged artifact must be a regular non-symlink file")
        if final.exists():
            raise StorageError(f"immutable artifact already exists: {final}")
        with staged.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        return {
            "staged_path": staged.relative_to(self.root).as_posix(),
            "final_path": final.relative_to(self.root).as_posix(),
            "sha256": digest,
            "expected_type": promotion.expected_type,
        }

    def _validate_promotions(self, record: Mapping[str, object]) -> None:
        validator = ArtifactValidator(self.root)
        for item in record.get("promotions", []):
            if not isinstance(item, Mapping):
                raise StorageError("promotion record must be an object")
            expected_type = item.get("expected_type")
            if expected_type is None:
                continue
            if not isinstance(expected_type, str) or not expected_type:
                raise StorageError("promotion expected_type must be a nonempty string")
            staged = self._task_path(
                self.root / str(item["staged_path"]), "staged_path", True
            )
            result = validator.validate_artifact(staged, expected_type)
            if not result.valid:
                raise StorageError("; ".join(result.errors))

    def _promote(self, record: Mapping[str, object]) -> None:
        for item in record.get("promotions", []):
            if not isinstance(item, Mapping):
                raise StorageError("promotion record must be an object")
            staged = self._task_path(self.root / str(item["staged_path"]), "staged_path", True)
            final = self._task_path(self.root / str(item["final_path"]), "final_path", False)
            if final.exists():
                raise StorageError(f"immutable artifact already exists: {final}")
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, final)

    def _remove_promoted_artifacts(self, record: Mapping[str, object]) -> None:
        for item in record.get("promotions", []):
            if not isinstance(item, Mapping):
                continue
            final = self._task_path(self.root / str(item["final_path"]), "final_path", False)
            if final.is_file() and not final.is_symlink():
                final.unlink()

    def _append_event_once(self, record: Mapping[str, object], revision: int) -> None:
        transaction_id = str(record["transaction_id"])
        if any(item.get("transaction_id") == transaction_id for item in self.storage.read_events()):
            return
        event = record.get("event")
        if not isinstance(event, Mapping):
            raise StorageError("transaction event must be an object")
        self.storage.append_event(
            {**dict(event), "transaction_id": transaction_id},
            state_revision=revision,
        )

    def _append_metric_once(self, record: Mapping[str, object], *, partial: bool) -> None:
        transaction_id = str(record["transaction_id"])
        if any(item.get("transaction_id") == transaction_id for item in self.storage.read_metrics()):
            return
        if partial:
            metric: dict[str, object] = {"measurement_status": "partial"}
        else:
            raw_metric = record.get("metric")
            metric = (
                {"measurement_status": "partial"}
                if raw_metric is None
                else dict(raw_metric)
            )
        self.storage.append_metric({**metric, "transaction_id": transaction_id})

    def _read_record(self, transaction_id: str) -> dict[str, Any]:
        return read_json_object(self._record_path(transaction_id))

    def _record_path(self, transaction_id: str) -> Path:
        return self.transactions_dir / f"{transaction_id}.json"

    def _task_path(self, path: Path, field_name: str, must_exist: bool) -> Path:
        requested = Path(path)
        if requested.is_symlink():
            raise StorageError(f"{field_name} must not be a symlink")
        resolved = requested.resolve(strict=must_exist)
        if resolved != self.root and self.root not in resolved.parents:
            raise StorageError(f"{field_name} escapes task root")
        return resolved

    @staticmethod
    def _revision(state: Mapping[str, object]) -> int:
        revision = state.get("state_revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise StorageError("state_revision must be a nonnegative integer")
        return revision

    @staticmethod
    def _validate_id(transaction_id: str) -> None:
        if not isinstance(transaction_id, str) or not _TRANSACTION_ID.fullmatch(transaction_id):
            raise StorageError("transaction_id is invalid")
