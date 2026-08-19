"""Real FFmpeg rendering and probing for Track B production runs."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path

from .media_layout import render_filter_for_media
from .storage import read_json_object

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


class MediaRuntimeError(RuntimeError):
    pass


class FFmpegMediaProbe:
    def __init__(self, executable: str = "ffprobe") -> None:
        self.executable = executable

    def __call__(self, path: Path) -> dict[str, object]:
        media = Path(path).resolve(strict=True)
        command = (
            self.executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,pix_fmt,sample_rate,channels",
            "-of",
            "json",
            str(media),
        )
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise MediaRuntimeError((result.stderr or "ffprobe failed")[:800])
        payload = json.loads(result.stdout)
        streams = payload.get("streams", [])
        video = next((row for row in streams if row.get("codec_type") == "video"), {})
        audio = next((row for row in streams if row.get("codec_type") == "audio"), {})
        return {
            "width": int(video.get("width", 0)),
            "height": int(video.get("height", 0)),
            "fps": _rate(video.get("avg_frame_rate")),
            "video_codec": video.get("codec_name"),
            "pixel_format": video.get("pix_fmt"),
            "video_stream_count": sum(row.get("codec_type") == "video" for row in streams),
            "audio_stream_count": sum(row.get("codec_type") == "audio" for row in streams),
            "audio_codec": audio.get("codec_name"),
            "audio_sample_rate": int(audio.get("sample_rate", 0) or 0),
            "audio_channels": int(audio.get("channels", 0) or 0),
            "duration_seconds": float(payload.get("format", {}).get("duration", 0.0)),
        }


class FFmpegRenderer:
    def __init__(self, executable: str = "ffmpeg") -> None:
        self.executable = executable

    def __call__(
        self,
        *,
        output_path: Path,
        timeline: Mapping[str, object],
        material_manifest: Path,
        captions_path: Path,
        profile: Mapping[str, object],
    ) -> dict[str, object]:
        del captions_path
        manifest_path = Path(material_manifest).resolve(strict=True)
        task_root = manifest_path.parent
        manifest = read_json_object(manifest_path)
        rows = timeline.get("fragments")
        materials = manifest.get("fragments")
        if not isinstance(rows, list) or not rows or not isinstance(materials, list):
            raise MediaRuntimeError("timeline and material fragments are required")
        by_id = {
            str(row["fragment_id"]): row
            for row in materials
            if isinstance(row, Mapping) and isinstance(row.get("fragment_id"), str)
        }
        width = int(profile.get("width", 0))
        height = int(profile.get("height", 0))
        fps = int(profile.get("fps", 0))
        duration = float(timeline.get("duration_seconds", 0))
        if min(width, height, fps) <= 0 or duration <= 0:
            raise MediaRuntimeError("render profile and duration are invalid")
        overlay_policy: dict[str, str] = {}
        plan_path = task_root / "fragment_plan.json"
        if plan_path.is_file() and not plan_path.is_symlink():
            plan_rows = read_json_object(plan_path).get("fragments", [])
            if isinstance(plan_rows, list):
                overlay_policy = {
                    str(row.get("fragment_id")): str(row.get("overlay_policy", ""))
                    for row in plan_rows
                    if isinstance(row, Mapping) and isinstance(row.get("fragment_id"), str)
                }
        voice_manifest = read_json_object(task_root / "voice" / "voice_manifest.json")
        final_voice = voice_manifest.get("final_voice")
        if not isinstance(final_voice, Mapping) or not isinstance(final_voice.get("path"), str):
            raise MediaRuntimeError("final approved voice is required")
        voice_path = (task_root / "voice" / str(final_voice["path"])).resolve(strict=True)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        inputs: list[str] = []
        labels: list[str] = []
        filters: list[str] = []
        for index, raw in enumerate(rows):
            if not isinstance(raw, Mapping):
                raise MediaRuntimeError("timeline fragment is invalid")
            fragment_id = str(raw.get("fragment_id", ""))
            material = by_id.get(fragment_id)
            if material is None:
                raise MediaRuntimeError(f"material is missing for {fragment_id}")
            path = (task_root / str(material.get("material_path", ""))).resolve(strict=True)
            fragment_duration = float(raw.get("timeline_end_seconds", 0)) - float(
                raw.get("timeline_start_seconds", 0)
            )
            if fragment_duration <= 0:
                raise MediaRuntimeError(f"timeline duration is invalid for {fragment_id}")
            if path.suffix.lower() in _IMAGE_EXTS:
                inputs.extend(("-loop", "1", "-t", f"{fragment_duration:.6f}", "-i", str(path)))
            else:
                start = float(raw.get("source_start_seconds", 0))
                inputs.extend(("-ss", f"{start:.6f}", "-t", f"{fragment_duration:.6f}", "-i", str(path)))
            label = f"v{index}"
            filter_chain = render_filter_for_media(
                suffix=path.suffix,
                overlay_policy=overlay_policy.get(fragment_id),
                canvas_width=width,
                canvas_height=height,
            )
            filters.append(
                f"[{index}:v]{filter_chain},fps={fps},trim=duration={fragment_duration:.6f},"
                f"setpts=PTS-STARTPTS,format=yuv420p[{label}]"
            )
            labels.append(f"[{label}]")
        filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[outv]")
        with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
            silent = Path(temporary) / "silent.mp4"
            video_command = (
                self.executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                *inputs,
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[outv]",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(fps),
                "-movflags",
                "+faststart",
                str(silent),
            )
            _run(video_command)
            mux_command = (
                self.executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(silent),
                "-i",
                str(voice_path),
                "-t",
                f"{duration:.6f}",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(output),
            )
            _run(mux_command)
        return {
            "engine": "ffmpeg",
            "fragment_count": len(rows),
            "profile": {"width": width, "height": height, "fps": fps},
        }


class FFmpegProxyRenderer:
    def __init__(self, task_root: Path, executable: str = "ffmpeg") -> None:
        self.task_root = Path(task_root).resolve(strict=True)
        self.renderer = FFmpegRenderer(executable)

    def __call__(
        self, *, timeline: Mapping[str, object], profile: Mapping[str, object]
    ) -> dict[str, object]:
        output = self.task_root / "proxy.mp4"
        details = self.renderer(
            output_path=output,
            timeline=timeline,
            material_manifest=self.task_root / "material_manifest.json",
            captions_path=self.task_root / "captions.srt",
            profile=profile,
        )
        return {**details, "path": "proxy.mp4"}


class FFprobeDuration:
    def __init__(self, executable: str = "ffprobe") -> None:
        self.executable = executable

    def __call__(self, path: Path) -> float:
        command = (
            self.executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(Path(path).resolve(strict=True)),
        )
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise MediaRuntimeError((result.stderr or "duration probe failed")[:800])
        return float(result.stdout.strip())


class FFprobeFrameTimes:
    def __init__(self, executable: str = "ffprobe") -> None:
        self.executable = executable

    def __call__(self, path: Path) -> list[float]:
        command = (
            self.executable,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "frame=best_effort_timestamp_time",
            "-of",
            "csv=p=0",
            str(Path(path).resolve(strict=True)),
        )
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise MediaRuntimeError((result.stderr or "frame probe failed")[:800])
        return [float(line.strip().split(",", 1)[0]) for line in result.stdout.splitlines() if line.strip()]


def _run(command: tuple[str, ...]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MediaRuntimeError((result.stderr or "FFmpeg failed")[:1200])


def _rate(value: object) -> int | float:
    raw = str(value or "0/1")
    numerator, denominator = raw.split("/", 1)
    result = float(numerator) / float(denominator)
    return int(result) if result.is_integer() else result


__all__ = [
    "FFmpegMediaProbe",
    "FFmpegProxyRenderer",
    "FFmpegRenderer",
    "FFprobeDuration",
    "FFprobeFrameTimes",
    "MediaRuntimeError",
]
