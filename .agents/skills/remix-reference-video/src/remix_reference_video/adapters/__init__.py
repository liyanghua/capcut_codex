"""Declarative manifests for Track B stage adapters."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..storage import StorageError


def content_fingerprint(
    execution_stage_id: str,
    implementation_version: str,
    inputs: tuple[Path, ...],
) -> str:
    """Hash an adapter identity and only its explicitly registered inputs."""

    records: list[dict[str, object]] = []
    for input_path in inputs:
        path = Path(input_path)
        if path.is_symlink():
            raise StorageError(f"adapter input must not be a symlink: {path}")
        resolved = path.resolve(strict=True)
        if resolved.is_file():
            records.append(_file_record(resolved, resolved.name, hash_content=True))
            continue
        if not resolved.is_dir():
            raise StorageError(f"adapter input must be a file or directory: {resolved}")
        for child in sorted(resolved.rglob("*")):
            if child.is_symlink() or not child.is_file():
                continue
            records.append(
                _file_record(
                    child,
                    child.relative_to(resolved).as_posix(),
                    hash_content=False,
                )
            )
    payload = {
        "execution_stage_id": execution_stage_id,
        "implementation_version": implementation_version,
        "inputs": records,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_record(path: Path, name: str, *, hash_content: bool) -> dict[str, object]:
    stat = path.stat()
    record: dict[str, object] = {
        "path": name,
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns,
    }
    if hash_content:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        record["sha256"] = digest.hexdigest()
    return record


__all__ = ["content_fingerprint"]
