from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from remix_reference_video.asset_index import (
    AssetIndexPrerequisiteError,
    AssetIndexRetryableError,
    AssetIndexer,
)


class RecordingProbe:
    def __init__(self, unreadable_names: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.unreadable_names = unreadable_names or set()

    def __call__(self, path: Path, media_type: str) -> dict[str, object]:
        self.calls.append((path.name, media_type))
        if path.name in self.unreadable_names:
            raise ValueError("fixture media is unreadable")
        return {"media_type": media_type, "size": path.stat().st_size}


class AssetIndexerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.assets = self.root / "assets"
        self.assets.mkdir()
        self.database = self.root / "cache" / "asset-index.sqlite3"

    def test_recursive_filtering_sha_deduplication_and_warm_cache(self) -> None:
        (self.assets / "a.mp4").write_bytes(b"same-video")
        nested = self.assets / "nested"
        nested.mkdir()
        (nested / "duplicate.MOV").write_bytes(b"same-video")
        (nested / "still.jpg").write_bytes(b"still")
        (nested / "notes.txt").write_text("ignore", encoding="utf-8")
        probe = RecordingProbe()
        indexer = AssetIndexer(self.database, probe=probe)

        cold = indexer.index(self.assets)
        warm = indexer.index(self.assets)

        self.assertEqual(cold.discovered_files, 4)
        self.assertEqual(cold.supported_files, 3)
        self.assertEqual(cold.unsupported_files, 1)
        self.assertEqual(cold.hashed_files, 3)
        self.assertEqual(cold.probed_contents, 2)
        self.assertEqual(cold.deduplicated_files, 1)
        self.assertEqual(cold.cache_hits, 0)
        self.assertEqual(warm.cache_hits, 3)
        self.assertEqual(warm.hashed_files, 0)
        self.assertEqual(warm.probed_contents, 0)
        self.assertEqual(len(probe.calls), 2)
        self.assertEqual(len(indexer.files(self.assets)), 3)

    def test_changed_file_is_rehashed_and_removed_file_is_invalidated(self) -> None:
        media = self.assets / "clip.mp4"
        media.write_bytes(b"version-one")
        probe = RecordingProbe()
        indexer = AssetIndexer(self.database, probe=probe)
        indexer.index(self.assets)
        first_sha = indexer.files(self.assets)[0]["sha256"]

        previous = media.stat().st_mtime_ns
        media.write_bytes(b"version-two")
        os.utime(media, ns=(previous + 1_000_000, previous + 1_000_000))
        changed = indexer.index(self.assets)
        second_sha = indexer.files(self.assets)[0]["sha256"]

        self.assertEqual(changed.hashed_files, 1)
        self.assertEqual(changed.probed_contents, 1)
        self.assertNotEqual(first_sha, second_sha)
        media.unlink()
        removed = indexer.index(self.assets)
        self.assertEqual(removed.removed_files, 1)
        self.assertEqual(indexer.files(self.assets), [])

    def test_unreadable_media_is_recorded_and_reused_without_reprobe(self) -> None:
        (self.assets / "broken.mp4").write_bytes(b"not-media")
        probe = RecordingProbe({"broken.mp4"})
        indexer = AssetIndexer(self.database, probe=probe)

        cold = indexer.index(self.assets)
        warm = indexer.index(self.assets)

        self.assertEqual(cold.unreadable_files, 1)
        self.assertEqual(warm.unreadable_files, 1)
        self.assertEqual(warm.cache_hits, 1)
        self.assertEqual(len(probe.calls), 1)
        record = indexer.files(self.assets)[0]
        self.assertEqual(record["probe_status"], "unreadable")
        self.assertIn("unreadable", record["error"])

    def test_filesystem_read_failure_is_persisted_and_cleared_after_recovery(self) -> None:
        media = self.assets / "permission-denied.mp4"
        media.write_bytes(b"media")
        indexer = AssetIndexer(self.database, probe=RecordingProbe())

        with patch(
            "remix_reference_video.asset_index._sha256_file",
            side_effect=PermissionError("permission denied"),
        ):
            summary = indexer.index(self.assets)

        self.assertEqual(summary.unreadable_files, 1)
        errors = indexer.scan_errors(self.assets)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["relative_path"], "permission-denied.mp4")
        self.assertIn("PermissionError", errors[0]["error"])
        self.assertEqual(indexer.files(self.assets), [])

        recovered = indexer.index(self.assets)
        self.assertEqual(recovered.unreadable_files, 0)
        self.assertEqual(indexer.scan_errors(self.assets), [])
        self.assertEqual(len(indexer.files(self.assets)), 1)

    def test_probe_environment_failure_is_not_cached_as_unreadable_media(self) -> None:
        media = self.assets / "clip.mp4"
        media.write_bytes(b"media")

        def unavailable_probe(path: Path, media_type: str) -> dict[str, object]:
            raise AssetIndexPrerequisiteError("ffprobe disappeared")

        indexer = AssetIndexer(self.database, probe=unavailable_probe)
        with self.assertRaises(AssetIndexPrerequisiteError):
            indexer.index(self.assets)

        indexer.probe = RecordingProbe()
        recovered = indexer.index(self.assets)
        self.assertEqual(recovered.unreadable_files, 0)
        self.assertEqual(recovered.probed_contents, 1)
        self.assertEqual(indexer.files(self.assets)[0]["probe_status"], "ready")

    def test_retryable_probe_failure_is_recorded_by_path_and_retried(self) -> None:
        media = self.assets / "slow.mp4"
        media.write_bytes(b"media")
        attempts = 0

        def flaky_probe(path: Path, media_type: str) -> dict[str, object]:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise AssetIndexRetryableError("ffprobe timed out")
            return {"media_type": media_type, "size": path.stat().st_size}

        indexer = AssetIndexer(self.database, probe=flaky_probe)
        first = indexer.index(self.assets)
        second = indexer.index(self.assets)

        self.assertEqual(first.unreadable_files, 1)
        self.assertEqual(first.probed_contents, 1)
        self.assertEqual(second.unreadable_files, 0)
        self.assertEqual(second.probed_contents, 1)
        self.assertEqual(attempts, 2)
        self.assertEqual(indexer.scan_errors(self.assets), [])
        self.assertEqual(indexer.files(self.assets)[0]["probe_status"], "ready")

    def test_symlinks_outside_asset_root_are_not_indexed(self) -> None:
        outside = self.root / "outside.mp4"
        outside.write_bytes(b"outside")
        (self.assets / "escape.mp4").symlink_to(outside)
        probe = RecordingProbe()

        summary = AssetIndexer(self.database, probe=probe).index(self.assets)

        self.assertEqual(summary.discovered_files, 0)
        self.assertEqual(summary.supported_files, 0)
        self.assertEqual(probe.calls, [])

    def test_database_inside_read_only_asset_root_is_rejected_before_write(self) -> None:
        database = self.assets / "asset-index.sqlite3"

        with self.assertRaisesRegex(ValueError, "outside.*asset root"):
            AssetIndexer(database, probe=RecordingProbe()).index(self.assets)

        self.assertFalse(database.exists())
        self.assertEqual(list(self.assets.iterdir()), [])

    def test_every_sqlite_connection_is_closed_after_public_operations(self) -> None:
        (self.assets / "clip.mp4").write_bytes(b"media")
        real_connect = sqlite3.connect
        connections: list[sqlite3.Connection] = []

        def tracking_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
            connection = real_connect(*args, **kwargs)
            connections.append(connection)
            return connection

        with patch(
            "remix_reference_video.asset_index.sqlite3.connect",
            side_effect=tracking_connect,
        ):
            indexer = AssetIndexer(self.database, probe=RecordingProbe())
            indexer.index(self.assets)
            indexer.files(self.assets)

        self.assertGreaterEqual(len(connections), 3)
        for connection in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
