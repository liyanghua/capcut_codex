from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from remix_reference_video.storage import RevisionConflict, TaskStorage
from remix_reference_video.transactions import ArtifactPromotion, TransactionManager


class TransactionManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.store = TaskStorage(self.root)
        self.store.initialize_state(
            {
                "run_id": "run-1",
                "state_revision": 0,
                "gate_status": {"gate1": "not_ready"},
                "blockers": [],
            }
        )
        self.manager = TransactionManager(self.store)

    def prepare(self, transaction_id: str = "tx-1") -> dict[str, object]:
        staging = self.root / ".staging" / transaction_id / "result.json"
        staging.parent.mkdir(parents=True)
        staging.write_text('{"ok":true}\n', encoding="utf-8")
        return self.manager.prepare(
            transaction_id=transaction_id,
            expected_revision=0,
            state_changes={"active_stage": "blueprint"},
            event={"event_type": "stage.completed"},
            metric={"machine_seconds": 1.25, "measurement_status": "measured"},
            promotions=(
                ArtifactPromotion(
                    staged_path=staging,
                    final_path=self.root / "versions" / transaction_id / "result.json",
                ),
            ),
        )

    def test_commit_promotes_artifact_and_records_state_event_and_metric(self) -> None:
        prepared = self.prepare()
        committed = self.manager.commit("tx-1")

        self.assertEqual(prepared["status"], "prepared")
        self.assertEqual(committed["status"], "committed")
        self.assertEqual(self.store.read_state()["state_revision"], 1)
        self.assertTrue((self.root / "versions/tx-1/result.json").is_file())
        self.assertEqual(self.store.read_events()[0]["transaction_id"], "tx-1")
        self.assertEqual(self.store.read_metrics()[0]["transaction_id"], "tx-1")

    def test_reconcile_rolls_back_orphan_when_state_is_still_before(self) -> None:
        self.prepare()
        final = self.root / "versions/tx-1/result.json"
        final.parent.mkdir(parents=True)
        final.write_text("orphan", encoding="utf-8")

        result = self.manager.reconcile("tx-1")

        self.assertEqual(result["status"], "rolled_back")
        self.assertFalse(final.exists())
        self.assertEqual(self.store.read_state()["state_revision"], 0)

    def test_reconcile_repairs_event_and_partial_metric_after_state_commit(self) -> None:
        self.prepare()
        self.store.update_state(lambda state: state | {"active_stage": "blueprint"})

        first = self.manager.reconcile("tx-1")
        second = self.manager.reconcile("tx-1")

        self.assertEqual(first["status"], "committed")
        self.assertEqual(second["status"], "committed")
        self.assertEqual(len(self.store.read_events()), 1)
        self.assertEqual(len(self.store.read_metrics()), 1)
        self.assertEqual(
            self.store.read_metrics()[0]["measurement_status"], "partial"
        )
        self.assertNotIn("machine_seconds", self.store.read_metrics()[0])

    def test_prepare_rejects_stale_revision(self) -> None:
        self.store.update_state(lambda state: state)

        with self.assertRaises(RevisionConflict):
            self.prepare()

    def test_transaction_record_is_durable_json(self) -> None:
        self.prepare()

        record = json.loads(
            (self.root / ".transactions/tx-1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record["state_revision_before"], 0)
        self.assertEqual(record["state_revision_after"], 1)
        self.assertEqual(record["status"], "prepared")


if __name__ == "__main__":
    unittest.main()
