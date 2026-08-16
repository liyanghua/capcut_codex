"""Incremental SQLite-backed technical index for reusable media assets."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import time
import uuid
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


VIDEO_EXTENSIONS = frozenset({".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"})
IMAGE_EXTENSIONS = frozenset({".gif", ".heic", ".jpeg", ".jpg", ".png", ".webp"})
ASSET_INDEX_IMPLEMENTATION_VERSION = "asset-index-v2"


class AssetIndexPrerequisiteError(RuntimeError):
    """Raised when a required local indexing tool is unavailable."""


class AssetIndexRetryableError(RuntimeError):
    """Raised when probing may succeed on a later scan without file changes."""


@dataclass(frozen=True, slots=True)
class IndexSummary:
    implementation_version: str
    discovered_files: int
    supported_files: int
    unsupported_files: int
    cache_hits: int
    hashed_files: int
    probed_contents: int
    deduplicated_files: int
    unreadable_files: int
    removed_files: int
    elapsed_seconds: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class FFprobeAdapter:
    """Return a compact technical projection without persisting process output."""

    def __init__(self, executable: str = "ffprobe", timeout_seconds: float = 30.0) -> None:
        located = shutil.which(executable)
        if located is None:
            raise AssetIndexPrerequisiteError(
                f"FFprobe executable not found: {executable}"
            )
        self.executable = str(Path(located).resolve())
        self.timeout_seconds = timeout_seconds

    def __call__(self, path: Path, media_type: str) -> dict[str, object]:
        try:
            completed = subprocess.run(
                [
                    self.executable,
                    "-v",
                    "error",
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    str(path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise AssetIndexRetryableError("ffprobe timed out") from error
        except OSError as error:
            raise AssetIndexPrerequisiteError(
                f"FFprobe could not be executed: {error}"
            ) from error
        if completed.returncode != 0:
            raise ValueError(f"ffprobe failed with exit code {completed.returncode}")
        try:
            payload = json.loads(completed.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("ffprobe returned invalid JSON") from error
        streams = payload.get("streams", [])
        if not isinstance(streams, list):
            raise ValueError("ffprobe streams must be an array")
        visual = next(
            (stream for stream in streams if stream.get("codec_type") == "video"), None
        )
        if not isinstance(visual, dict):
            raise ValueError("media has no visual stream")
        format_data = payload.get("format", {})
        if not isinstance(format_data, dict):
            format_data = {}
        return {
            "media_type": media_type,
            "codec_name": visual.get("codec_name"),
            "width": visual.get("width"),
            "height": visual.get("height"),
            "frame_rate": visual.get("avg_frame_rate") or visual.get("r_frame_rate"),
            "duration_seconds": _number_or_none(
                visual.get("duration") or format_data.get("duration")
            ),
            "has_audio": any(
                stream.get("codec_type") == "audio"
                for stream in streams
                if isinstance(stream, dict)
            ),
            "format_name": format_data.get("format_name"),
        }


def _number_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AssetIndexer:
    """Index media by path identity while deduplicating technical facts by content SHA."""

    def __init__(
        self,
        database_path: Path,
        *,
        probe: Callable[[Path, str], dict[str, object]] | None = None,
        implementation_version: str = ASSET_INDEX_IMPLEMENTATION_VERSION,
    ) -> None:
        if not isinstance(implementation_version, str) or not implementation_version:
            raise ValueError("asset index implementation_version is required")
        self.database_path = Path(database_path).resolve(strict=False)
        self.probe = probe or FFprobeAdapter()
        self.implementation_version = implementation_version
        self._database_initialized = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize_database(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS contents (
                    sha256 TEXT PRIMARY KEY,
                    media_type TEXT NOT NULL,
                    probe_status TEXT NOT NULL,
                    probe_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS files (
                    asset_root TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    ctime_ns INTEGER NOT NULL,
                    sha256 TEXT NOT NULL REFERENCES contents(sha256),
                    media_type TEXT NOT NULL,
                    last_seen_scan TEXT NOT NULL,
                    PRIMARY KEY (asset_root, relative_path)
                );
                CREATE INDEX IF NOT EXISTS files_sha256_idx ON files(sha256);
                CREATE TABLE IF NOT EXISTS scan_errors (
                    asset_root TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    error TEXT NOT NULL,
                    last_seen_scan TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (asset_root, relative_path)
                );
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            current = connection.execute(
                "SELECT value FROM metadata WHERE key = 'implementation_version'"
            ).fetchone()
            if current is None or current[0] != self.implementation_version:
                connection.execute("DELETE FROM files")
                connection.execute("DELETE FROM scan_errors")
                connection.execute("DELETE FROM contents")
            connection.execute(
                """INSERT INTO metadata(key, value) VALUES ('schema_version', '2')
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value"""
            )
            connection.execute(
                """INSERT INTO metadata(key, value)
                   VALUES ('implementation_version', ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (self.implementation_version,),
            )

    def _prepare_database(self, asset_root: Path) -> Path:
        root = Path(asset_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"asset root must be a directory: {root}")
        if self.database_path == root or root in self.database_path.parents:
            raise ValueError(
                f"database path must remain outside asset root: {self.database_path}"
            )
        if not self._database_initialized:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize_database()
            self._database_initialized = True
        return root

    def index(self, asset_root: Path) -> IndexSummary:
        started = time.perf_counter()
        root = self._prepare_database(asset_root)
        root_key = str(root)
        scan_id = str(uuid.uuid4())
        discovered = supported = unsupported = 0
        cache_hits = hashed = probed = deduplicated = unreadable = 0

        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = {
                row["relative_path"]: row
                for row in connection.execute(
                    """
                    SELECT f.relative_path, f.size_bytes, f.mtime_ns, f.ctime_ns,
                           f.sha256, c.probe_status
                    FROM files AS f
                    JOIN contents AS c ON c.sha256 = f.sha256
                    WHERE f.asset_root = ?
                    """,
                    (root_key,),
                )
            }
            for path in sorted(root.rglob("*")):
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    resolved = path.resolve(strict=True)
                except OSError:
                    continue
                if resolved != root and root not in resolved.parents:
                    continue
                discovered += 1
                media_type = self._media_type(path)
                if media_type is None:
                    unsupported += 1
                    continue
                supported += 1
                relative = path.relative_to(root).as_posix()
                try:
                    stat = path.stat()
                except OSError as error:
                    unreadable += 1
                    self._record_scan_error(
                        connection, root_key, relative, media_type, scan_id, error
                    )
                    continue
                prior = existing.get(relative)
                if (
                    prior is not None
                    and prior["size_bytes"] == stat.st_size
                    and prior["mtime_ns"] == stat.st_mtime_ns
                    and prior["ctime_ns"] == stat.st_ctime_ns
                ):
                    cache_hits += 1
                    if prior["probe_status"] == "unreadable":
                        unreadable += 1
                    connection.execute(
                        """UPDATE files SET last_seen_scan = ?
                           WHERE asset_root = ? AND relative_path = ?""",
                        (scan_id, root_key, relative),
                    )
                    continue

                try:
                    digest = _sha256_file(path)
                except OSError as error:
                    unreadable += 1
                    self._record_scan_error(
                        connection, root_key, relative, media_type, scan_id, error
                    )
                    continue
                hashed += 1
                content = connection.execute(
                    "SELECT probe_status FROM contents WHERE sha256 = ?", (digest,)
                ).fetchone()
                if content is None:
                    probed += 1
                    try:
                        probe_data = self.probe(path, media_type)
                        probe_status = "ready"
                        probe_json = json.dumps(
                            probe_data,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                        error = None
                    except AssetIndexPrerequisiteError:
                        raise
                    except AssetIndexRetryableError as probe_error:
                        unreadable += 1
                        self._record_scan_error(
                            connection,
                            root_key,
                            relative,
                            media_type,
                            scan_id,
                            probe_error,
                        )
                        continue
                    except Exception as probe_error:
                        probe_status = "unreadable"
                        probe_json = None
                        error = f"{type(probe_error).__name__}: {probe_error}"[:500]
                    connection.execute(
                        """INSERT INTO contents
                           (sha256, media_type, probe_status, probe_json, error)
                           VALUES (?, ?, ?, ?, ?)""",
                        (digest, media_type, probe_status, probe_json, error),
                    )
                else:
                    deduplicated += 1
                    probe_status = content["probe_status"]
                if probe_status == "unreadable":
                    unreadable += 1
                connection.execute(
                    """
                    INSERT INTO files
                      (asset_root, relative_path, size_bytes, mtime_ns, ctime_ns,
                       sha256, media_type, last_seen_scan)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(asset_root, relative_path) DO UPDATE SET
                      size_bytes = excluded.size_bytes,
                      mtime_ns = excluded.mtime_ns,
                      ctime_ns = excluded.ctime_ns,
                      sha256 = excluded.sha256,
                      media_type = excluded.media_type,
                      last_seen_scan = excluded.last_seen_scan
                    """,
                    (
                        root_key,
                        relative,
                        stat.st_size,
                        stat.st_mtime_ns,
                        stat.st_ctime_ns,
                        digest,
                        media_type,
                        scan_id,
                    ),
                )
            removed = connection.execute(
                "DELETE FROM files WHERE asset_root = ? AND last_seen_scan <> ?",
                (root_key, scan_id),
            ).rowcount
            connection.execute(
                "DELETE FROM scan_errors WHERE asset_root = ? AND last_seen_scan <> ?",
                (root_key, scan_id),
            )

        return IndexSummary(
            implementation_version=self.implementation_version,
            discovered_files=discovered,
            supported_files=supported,
            unsupported_files=unsupported,
            cache_hits=cache_hits,
            hashed_files=hashed,
            probed_contents=probed,
            deduplicated_files=deduplicated,
            unreadable_files=unreadable,
            removed_files=max(removed, 0),
            elapsed_seconds=round(time.perf_counter() - started, 6),
        )

    def files(self, asset_root: Path) -> list[dict[str, Any]]:
        root = str(self._prepare_database(asset_root))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT f.relative_path, f.size_bytes, f.mtime_ns, f.ctime_ns,
                       f.sha256, f.media_type, c.probe_status, c.probe_json, c.error
                FROM files AS f
                JOIN contents AS c ON c.sha256 = f.sha256
                WHERE f.asset_root = ?
                ORDER BY f.relative_path
                """,
                (root,),
            ).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            probe_json = record.pop("probe_json")
            record["probe"] = json.loads(probe_json) if probe_json is not None else None
            records.append(record)
        return records

    def scan_errors(self, asset_root: Path) -> list[dict[str, Any]]:
        """Return current path-level read failures from the latest asset scan."""

        root = str(self._prepare_database(asset_root))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT relative_path, media_type, error, updated_at
                FROM scan_errors
                WHERE asset_root = ?
                ORDER BY relative_path
                """,
                (root,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _record_scan_error(
        connection: sqlite3.Connection,
        asset_root: str,
        relative_path: str,
        media_type: str,
        scan_id: str,
        error: OSError,
    ) -> None:
        message = f"{type(error).__name__}: {error}"[:500]
        connection.execute(
            """
            INSERT INTO scan_errors
              (asset_root, relative_path, media_type, error, last_seen_scan)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(asset_root, relative_path) DO UPDATE SET
              media_type = excluded.media_type,
              error = excluded.error,
              last_seen_scan = excluded.last_seen_scan,
              updated_at = CURRENT_TIMESTAMP
            """,
            (asset_root, relative_path, media_type, message, scan_id),
        )

    @staticmethod
    def _media_type(path: Path) -> str | None:
        suffix = path.suffix.lower()
        if suffix in VIDEO_EXTENSIONS:
            return "video"
        if suffix in IMAGE_EXTENSIONS:
            return "image"
        return None
