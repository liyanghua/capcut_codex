"""Shared safe path resolution for frozen asset snapshots."""

from __future__ import annotations

from pathlib import Path


RELATIVE_PATH_V1 = "relative_path_v1"


class PathContractError(ValueError):
    pass


def resolve_asset_snapshot_path(
    asset_root: Path, key: str, contract_version: str | None
) -> Path:
    requested_root = Path(asset_root)
    if requested_root.is_symlink():
        raise PathContractError("asset root must not be a symlink")
    try:
        root = requested_root.resolve(strict=True)
    except OSError as error:
        raise PathContractError("asset root is missing") from error
    if not root.is_dir():
        raise PathContractError("asset root must be a directory")
    if not isinstance(key, str) or not key:
        raise PathContractError("frozen asset key is invalid")
    if contract_version is None:
        if Path(key).name != key or "/" in key or "\\" in key:
            raise PathContractError("legacy frozen assets must be direct children")
        parts = (key,)
    elif contract_version == RELATIVE_PATH_V1:
        if key.startswith("/") or "\\" in key:
            raise PathContractError("frozen asset key must be relative POSIX")
        parts = tuple(key.split("/"))
        if any(part in {"", ".", ".."} for part in parts):
            raise PathContractError("frozen asset key contains an unsafe segment")
    else:
        raise PathContractError("unsupported asset snapshot contract version")
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            raise PathContractError("frozen asset path must not contain a symlink")
    try:
        resolved = current.resolve(strict=True)
    except OSError as error:
        raise PathContractError(f"frozen asset is missing: {key}") from error
    if root not in resolved.parents or not resolved.is_file():
        raise PathContractError(f"frozen asset is not a regular file: {key}")
    return resolved


__all__ = ["PathContractError", "RELATIVE_PATH_V1", "resolve_asset_snapshot_path"]
