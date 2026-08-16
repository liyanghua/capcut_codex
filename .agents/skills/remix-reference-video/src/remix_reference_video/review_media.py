"""Generate hash-bound Gate 3 contact sheets and broad-range proxies."""

from __future__ import annotations

import hashlib
import math
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

from .storage import atomic_write_json, read_json_object


def build_gate3_review_media(
    *, task_root: Path, asset_root: Path, package_path: Path
) -> dict[str, object]:
    task = Path(task_root).resolve(strict=True)
    assets = Path(asset_root).resolve(strict=True)
    package_file = Path(package_path).resolve(strict=True)
    if task not in package_file.parents:
        raise ValueError("Gate 3 package escapes task root")
    package = read_json_object(package_file)
    selections = package.get("selections")
    if package.get("gate_id") != "gate3_material_selection" or not isinstance(selections, list):
        raise ValueError("Gate 3 material selection package is required")
    frames = task / "gate3_review_frames"
    proxies = task / "gate3_review_proxies"
    frames.mkdir(exist_ok=True)
    proxies.mkdir(exist_ok=True)
    proxy_paths: list[str] = []
    for selection in selections:
        if not isinstance(selection, Mapping):
            raise ValueError("Gate 3 selection is invalid")
        fragment_id = str(selection.get("fragment_id", ""))
        relative = selection.get("source_path")
        broad = selection.get("approved_broad_range")
        if not fragment_id or not isinstance(relative, str) or not isinstance(broad, Mapping):
            raise ValueError("Gate 3 selection is incomplete")
        source = (assets / relative).resolve(strict=True)
        if assets not in source.parents or source.is_symlink():
            raise ValueError("Gate 3 source escapes asset root")
        start, end = float(broad["start_seconds"]), float(broad["end_seconds"])
        if start < 0 or end <= start:
            raise ValueError("Gate 3 broad range is invalid")
        frame = frames / f"{fragment_id}.jpg"
        image = source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
        if not image:
            command.extend(("-ss", f"{(start + end) / 2:.6f}"))
        command.extend(("-i", str(source), "-frames:v", "1", "-vf",
            "scale=360:640:force_original_aspect_ratio=increase,crop=360:640", "-q:v", "2", str(frame)))
        _run(command)
        if not image:
            proxy = proxies / f"{fragment_id}.mp4"
            _run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-ss", f"{start:.6f}", "-i", str(source), "-t", f"{end - start:.6f}",
                "-an", "-vf", "scale=360:640:force_original_aspect_ratio=increase,crop=360:640",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(proxy),
            ])
            proxy_paths.append(proxy.relative_to(task).as_posix())
    sheet = task / "gate3_review_contact_sheet.jpg"
    columns = min(4, max(1, math.ceil(math.sqrt(len(selections)))))
    rows = math.ceil(len(selections) / columns)
    frame_paths = [frames / f"{str(row['fragment_id'])}.jpg" for row in selections]
    if len(frame_paths) == 1:
        shutil.copy2(frame_paths[0], sheet)
    else:
        inputs = [item for frame in frame_paths for item in ("-i", str(frame))]
        layout = "|".join(
            f"{(index % columns) * 366}_{(index // columns) * 646}"
            for index in range(len(frame_paths))
        )
        labels = "".join(f"[{index}:v]" for index in range(len(frame_paths)))
        _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            *inputs, "-filter_complex",
            f"{labels}xstack=inputs={len(frame_paths)}:layout={layout}:fill=black[out]",
            "-map", "[out]", "-frames:v", "1", "-q:v", "2", str(sheet),
        ])
    review_paths = [sheet.relative_to(task).as_posix(), *proxy_paths]
    hashes = dict(package.get("input_hashes", {}))
    for relative in review_paths:
        hashes[relative] = _sha256(task / relative)
    package["input_hashes"] = hashes
    package["review_media"] = {
        "contact_sheet_path": sheet.relative_to(task).as_posix(),
        "proxy_paths": proxy_paths,
        "source_policy": "approved_broad_ranges_only",
    }
    atomic_write_json(package_file, package)
    return package


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "FFmpeg review media failed")[:1000])


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


__all__ = ["build_gate3_review_media"]
