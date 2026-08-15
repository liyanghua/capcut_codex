from __future__ import annotations

import json
import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from remix_reference_video.storage import (
    RevisionConflict,
    StorageError,
    TaskStorage,
    atomic_write_json,
)


def _append_events(task_root: str, worker_id: int, count: int) -> None:
    store = TaskStorage(Path(task_root))
    for index in range(count):
        store.append_event(
            {"event_type": "test.event", "worker_id": worker_id, "index": index},
            state_revision=0,
        )


class AtomicJsonTests(unittest.TestCase):
    def test_failed_replace_preserves_previous_json_and_cleans_staging_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            atomic_write_json(path, {"version": 1})

            with patch(
                "remix_reference_video.storage.os.replace",
                side_effect=OSError("injected replace failure"),
            ):
                with self.assertRaisesRegex(OSError, "injected"):
                    atomic_write_json(path, {"version": 2})

            self.assertEqual(json.loads(path.read_text()), {"version": 1})
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])


class TaskStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.task_root = Path(self._temporary.name).resolve()
        self.store = TaskStorage(self.task_root)
        self.store.initialize_state({"run_id": "fixture", "state_revision": 0})

    def test_state_updates_increment_revision_and_reject_stale_writer(self) -> None:
        first = self.store.update_state(
            lambda state: state | {"run_status": "running"},
            expected_revision=0,
        )
        second = self.store.update_state(
            lambda state: state | {"run_status": "awaiting_user"},
            expected_revision=1,
        )

        self.assertEqual(first["state_revision"], 1)
        self.assertEqual(second["state_revision"], 2)
        with self.assertRaises(RevisionConflict):
            self.store.update_state(lambda state: state, expected_revision=1)
        self.assertEqual(self.store.read_state()["state_revision"], 2)

    def test_event_append_is_process_locked_and_sequences_are_monotonic(self) -> None:
        process_count = 4
        events_per_process = 15
        context = multiprocessing.get_context("fork")
        processes = [
            context.Process(
                target=_append_events,
                args=(str(self.task_root), worker_id, events_per_process),
            )
            for worker_id in range(process_count)
        ]

        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=10)
            self.assertEqual(process.exitcode, 0)

        events = self.store.read_events()
        expected_count = process_count * events_per_process
        self.assertEqual(len(events), expected_count)
        self.assertEqual(
            [event["sequence"] for event in events],
            list(range(1, expected_count + 1)),
        )
        self.assertEqual(len({event["event_id"] for event in events}), expected_count)

    def test_metric_append_produces_complete_json_lines(self) -> None:
        self.store.append_metric(
            {
                "execution_stage_id": "probe-reference",
                "status": "succeeded",
                "elapsed_seconds": 0.25,
            }
        )

        metrics = self.store.read_metrics()
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0]["execution_stage_id"], "probe-reference")
        self.assertIn("recorded_at", metrics[0])

    def test_reconcile_appends_one_event_when_state_revision_has_no_event(self) -> None:
        self.store.append_event(
            {"event_type": "command.started"}, state_revision=0
        )
        self.store.update_state(lambda state: state | {"step": 1})
        self.store.update_state(lambda state: state | {"step": 2})

        reconciled = self.store.reconcile_event_gap()

        self.assertIsNotNone(reconciled)
        assert reconciled is not None
        self.assertEqual(reconciled["event_type"], "state.reconciled")
        self.assertEqual(reconciled["from_state_revision"], 0)
        self.assertEqual(reconciled["to_state_revision"], 2)
        self.assertEqual(reconciled["sequence"], 2)
        self.assertIsNone(self.store.reconcile_event_gap())

    def test_rejects_duplicate_keys_in_state_and_event_records(self) -> None:
        self.store.state_path.write_text(
            '{"run_id":"first","run_id":"second","state_revision":0}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(StorageError, "duplicate JSON key"):
            self.store.read_state()

        self.store.state_path.write_text(
            '{"run_id":"fixture","state_revision":0}', encoding="utf-8"
        )
        self.store.events_path.write_text(
            '{"sequence":1,"sequence":2}\n', encoding="utf-8"
        )
        with self.assertRaisesRegex(StorageError, "duplicate JSON key"):
            self.store.read_events()

    def test_rejects_invalid_utf8_without_masking_the_storage_error(self) -> None:
        self.store.state_path.write_bytes(b"\xff")

        with self.assertRaisesRegex(StorageError, "invalid JSON"):
            self.store.read_state()

    def test_rejects_symlinked_control_files_before_any_write(self) -> None:
        for name in (
            "pipeline_state.json",
            "pipeline_events.jsonl",
            "stage_metrics.jsonl",
            ".fast_path.lock",
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                outside = root / f"outside-{name.replace('.', '-') }"
                outside.write_bytes(b"outside")
                (root / name).symlink_to(outside)

                with self.assertRaisesRegex(StorageError, "symlink"):
                    TaskStorage(root)

                self.assertEqual(outside.read_bytes(), b"outside")

    def test_replaced_task_root_is_rejected_before_lock_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            root = parent / "task"
            root.mkdir()
            store = TaskStorage(root)
            original = parent / "original"
            root.rename(original)
            outside = parent / "outside"
            outside.mkdir()
            root.symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(StorageError, "task root"):
                with store.invocation_lock():
                    self.fail("unsafe task root lock was acquired")

            self.assertFalse((outside / ".fast_path.lock").exists())


if __name__ == "__main__":
    unittest.main()
