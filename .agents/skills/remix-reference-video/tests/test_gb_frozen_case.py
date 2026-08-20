from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from remix_reference_video.gb_frozen_case import (
    clone_declared_cold_cache,
    prepare_frozen_pair,
    prepare_tablemat_case,
    reuse_existing_hot_cache,
    validate_frozen_input,
)
from remix_reference_video.measurement import MeasurementError
from remix_reference_video.path_contracts import PathContractError, resolve_asset_snapshot_path
from remix_reference_video.storage import read_json_object


class GBFrozenCaseTests(unittest.TestCase):
    def test_relative_path_v1_resolves_nested_files_without_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            assets = root / "assets"
            nested = assets / "photos" / "detail.jpg"
            nested.parent.mkdir(parents=True)
            nested.write_bytes(b"detail")
            self.assertEqual(
                resolve_asset_snapshot_path(assets, "photos/detail.jpg", "relative_path_v1"),
                nested,
            )
            for invalid in ("/tmp/detail.jpg", "../detail.jpg", "photos/../detail.jpg", "photos\\detail.jpg"):
                with self.subTest(invalid):
                    with self.assertRaises(PathContractError):
                        resolve_asset_snapshot_path(assets, invalid, "relative_path_v1")
            link = assets / "linked"
            link.symlink_to(nested.parent, target_is_directory=True)
            with self.assertRaisesRegex(PathContractError, "symlink"):
                resolve_asset_snapshot_path(assets, "linked/detail.jpg", "relative_path_v1")

    def test_legacy_snapshot_keeps_direct_child_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            assets = Path(temporary).resolve()
            nested = assets / "photos" / "detail.jpg"
            nested.parent.mkdir()
            nested.write_bytes(b"detail")
            with self.assertRaisesRegex(PathContractError, "direct child"):
                resolve_asset_snapshot_path(assets, "photos/detail.jpg", None)

    def test_prepare_case_freezes_inputs_without_approvals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            for name in (
                "透明桌垫.mp4", "7月16日.mp4", "极简透明垫.mp4",
                "桌垫65度.jpg", "进口冰晶粒.jpg", "送发黄.jpg",
            ):
                (assets / name).write_bytes(name.encode())
            reference = root / "reference.mp4"
            reference.write_bytes(b"reference")
            task = root / "task"
            snapshot = prepare_tablemat_case(
                task_root=task,
                reference_source=reference,
                asset_root=assets,
            )
            self.assertEqual(snapshot["approval_records"], [])
            self.assertTrue((task / "reference-2026-08-16.mp4").is_file())
            self.assertEqual(
                len(read_json_object(task / "asset_profiles.json")["asset_profiles"]),
                11,
            )
            self.assertFalse((task / "pipeline_state.json").exists())
            self.assertFalse((task / "cache").exists())

    def test_pair_preparation_copies_only_frozen_inputs_and_keeps_approvals_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            for name in (
                "透明桌垫.mp4", "7月16日.mp4", "极简透明垫.mp4",
                "桌垫65度.jpg", "进口冰晶粒.jpg", "送发黄.jpg",
            ):
                (assets / name).write_bytes(name.encode())
            reference = root / "reference.mp4"
            reference.write_bytes(b"reference")
            frozen = root / "frozen"
            snapshot = prepare_tablemat_case(
                task_root=frozen,
                reference_source=reference,
                asset_root=assets,
            )
            (frozen / "pipeline_state.json").write_text("should not copy", encoding="utf-8")
            (frozen / "decisions").mkdir()
            (frozen / "decisions" / "gate1.json").write_text("approval", encoding="utf-8")
            cold, hot = root / "cold", root / "hot"
            result = prepare_frozen_pair(
                frozen_root=frozen,
                cold_root=cold,
                hot_root=hot,
                asset_root=assets,
            )
            self.assertFalse((cold / "pipeline_state.json").exists())
            self.assertFalse((hot / "decisions").exists())
            self.assertEqual(read_json_object(cold / "g_b_frozen_input_snapshot.json")["approval_records"], [])
            self.assertFalse(result["approval_reuse"])
            (cold / "cache" / "assets.sqlite3").write_bytes(b"index")
            clone = clone_declared_cold_cache(cold_root=cold, hot_root=hot)
            self.assertEqual(clone["file_count"], 1)
            self.assertEqual((hot / "cache" / "assets.sqlite3").read_bytes(), b"index")
            reused = clone_declared_cold_cache(cold_root=cold, hot_root=hot)
            self.assertEqual(reused["status"], "reused")

            (hot / "cache" / "assets.sqlite3").write_bytes(b"changed")
            with self.assertRaisesRegex(MeasurementError, "does not match"):
                clone_declared_cold_cache(cold_root=cold, hot_root=hot)

    def test_cache_clone_rejects_extra_entries_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cold, hot = root / "cold", root / "hot"
            (cold / "cache").mkdir(parents=True)
            (hot / "cache").mkdir(parents=True)
            (cold / "cache" / "assets.sqlite3").write_bytes(b"index")
            (hot / "cache" / "assets.sqlite3").write_bytes(b"index")
            (hot / "cache" / "extra").mkdir()
            with self.assertRaisesRegex(MeasurementError, "does not match"):
                clone_declared_cold_cache(cold_root=cold, hot_root=hot)

            (hot / "cache" / "extra").rmdir()
            (hot / "cache" / "link").symlink_to(hot / "cache" / "assets.sqlite3")
            with self.assertRaisesRegex(MeasurementError, "symlinks"):
                clone_declared_cold_cache(cold_root=cold, hot_root=hot)

    def test_existing_hot_cache_is_preserved_after_hot_index_updates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cold, hot = root / "cold", root / "hot"
            (cold / "cache").mkdir(parents=True)
            (hot / "cache").mkdir(parents=True)
            (cold / "cache" / "assets.sqlite3").write_bytes(b"cold-index")
            (hot / "cache" / "assets.sqlite3").write_bytes(b"hot-index-with-new-scan-id")

            result = reuse_existing_hot_cache(cold_root=cold, hot_root=hot)

            self.assertEqual(result["status"], "preserved")
            self.assertEqual((hot / "cache" / "assets.sqlite3").read_bytes(), b"hot-index-with-new-scan-id")

    def test_snapshot_hash_mismatch_blocks_pair_before_task_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            for name in (
                "透明桌垫.mp4", "7月16日.mp4", "极简透明垫.mp4",
                "桌垫65度.jpg", "进口冰晶粒.jpg", "送发黄.jpg",
            ):
                (assets / name).write_bytes(name.encode())
            reference = root / "reference.mp4"
            reference.write_bytes(b"reference")
            frozen = root / "frozen"
            prepare_tablemat_case(task_root=frozen, reference_source=reference, asset_root=assets)
            (frozen / "reference-2026-08-16.mp4").write_bytes(b"changed")
            with self.assertRaisesRegex(MeasurementError, "reference hash"):
                prepare_frozen_pair(
                    frozen_root=frozen,
                    cold_root=root / "cold",
                    hot_root=root / "hot",
                    asset_root=assets,
                )
            self.assertFalse((root / "cold").exists())


if __name__ == "__main__":
    unittest.main()
