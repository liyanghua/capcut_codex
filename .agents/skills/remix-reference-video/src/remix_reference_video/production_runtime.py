"""Concrete native completion registry for real G-B and production media."""

from __future__ import annotations

import sys
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters.asset_index import AssetIndexAdapter
from .adapters.reference_split import ReferenceSplitAdapter
from .media_runtime import (
    FFmpegMediaProbe,
    FFmpegProxyRenderer,
    FFmpegRenderer,
    FFprobeDuration,
    FFprobeFrameTimes,
)
from .native_completion import register_completion_adapters
from .native_planning import register_planning_adapters
from .native_preparation import register_preparation_adapters
from .native_registry import NativeAdapterRegistry
from .voice import DoubaoV3Provider


@dataclass(frozen=True, slots=True)
class ProductionRuntimeConfig:
    """Validated, non-secret inputs needed to build a real Native Registry."""

    reference_path: Path
    asset_root: Path
    brief_path: Path
    asset_profiles_path: Path
    cache_path: Path
    doubao_client_script: Path
    python_executable: str = sys.executable
    archive_root: Path | None = None

    @classmethod
    def from_file(cls, path: Path) -> "ProductionRuntimeConfig":
        config_path = Path(path).resolve(strict=True)
        if config_path.is_symlink() or not config_path.is_file():
            raise ValueError("runtime config must be a regular file")
        try:
            raw: Any = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("runtime config is not valid JSON") from error
        if not isinstance(raw, dict) or raw.get("artifact_type") != "production_runtime_config":
            raise ValueError("runtime config artifact_type is required")
        secret_fields = [
            str(key) for key in raw
            if any(token in str(key).lower() for token in ("key", "token", "secret", "password"))
        ]
        if secret_fields:
            raise ValueError("runtime config must not contain secret fields")
        paths = (
            "reference_path",
            "asset_root",
            "brief_path",
            "asset_profiles_path",
            "cache_path",
            "doubao_client_script",
        )
        values: dict[str, Path] = {}
        for name in paths:
            value = raw.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"runtime config requires {name}")
            candidate = (config_path.parent / value).resolve(strict=False)
            if candidate.is_symlink():
                raise ValueError(f"runtime config path must not be symlink: {name}")
            if name != "cache_path" and not candidate.exists():
                raise ValueError(f"runtime config path is missing: {name}")
            if name == "cache_path" and config_path.parent not in candidate.parents:
                raise ValueError("cache_path must remain inside the task directory")
            values[name] = candidate
        python_executable = raw.get("python_executable", sys.executable)
        if not isinstance(python_executable, str) or not python_executable.strip():
            raise ValueError("python_executable must be a nonempty string")
        archive = raw.get("archive_root")
        archive_root = None
        if archive is not None:
            if not isinstance(archive, str) or not archive.strip():
                raise ValueError("archive_root must be a nonempty string")
            archive_root = (config_path.parent / archive).resolve(strict=False)
            if config_path.parent not in archive_root.parents and archive_root != config_path.parent:
                raise ValueError("archive_root must remain inside the task directory")
        return cls(**values, python_executable=python_executable, archive_root=archive_root)


def register_real_completion_adapters(
    registry: NativeAdapterRegistry,
    *,
    asset_root: Path,
    doubao_client_script: Path,
    python_executable: str = sys.executable,
    archive_root: Path | None = None,
) -> NativeAdapterRegistry:
    root = registry.task_root
    return register_completion_adapters(
        registry,
        asset_root=asset_root,
        voice_provider=DoubaoV3Provider(
            client_script=doubao_client_script,
            python_executable=python_executable,
        ),
        voice_duration=FFprobeDuration(),
        proxy_renderer=FFmpegProxyRenderer(root),
        boundary_frame_times=FFprobeFrameTimes(),
        final_renderer=FFmpegRenderer(),
        media_probe=FFmpegMediaProbe(),
        archive_root=archive_root,
    )


def build_real_registry(
    *,
    task_root: Path,
    reference_path: Path,
    asset_root: Path,
    brief_path: Path,
    asset_profiles_path: Path,
    cache_path: Path,
    doubao_client_script: Path,
    python_executable: str = sys.executable,
    archive_root: Path | None = None,
) -> NativeAdapterRegistry:
    root = Path(task_root).resolve(strict=True)
    registry = NativeAdapterRegistry(root)
    registry.register(ReferenceSplitAdapter(root, reference_path))
    registry.register(AssetIndexAdapter(root, asset_root, cache_path))
    blueprint_input = root / "stage_inputs" / "compile-blueprint.json"
    register_preparation_adapters(
        registry,
        asset_profiles_path=asset_profiles_path,
        blueprint_stage_input_path=blueprint_input,
    )
    register_planning_adapters(
        registry,
        brief_path=brief_path,
        recipe_path=root / "recipe.json",
        coverage_precheck_path=root / "coverage_precheck.json",
        asset_profiles_path=asset_profiles_path,
    )
    register_real_completion_adapters(
        registry,
        asset_root=asset_root,
        doubao_client_script=doubao_client_script,
        python_executable=python_executable,
        archive_root=archive_root,
    )
    return registry


__all__ = ["build_real_registry", "register_real_completion_adapters"]
