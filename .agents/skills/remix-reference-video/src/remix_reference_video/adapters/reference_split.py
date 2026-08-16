"""Deterministic, task-local reference-video splitting."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..storage import StorageError, atomic_write_json, read_json_object
from . import content_fingerprint

_ENVELOPE = {
    "artifact_type": "recipe",
    "schema_id": "urn:capcut:remix-reference-video:artifact:recipe",
    "schema_version": "1.0.0",
    "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
}
_ATTEMPT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ReferenceSplitAdapter:
    execution_stage_id = "split-reference"
    implementation_version = "reference-split-v2"
    stop_gate = "gate1"

    def __init__(
        self,
        task_root: Path,
        reference_path: Path,
        *,
        scene_threshold: float = 0.3,
        ffmpeg: str | None = None,
        ffprobe: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        requested_root = Path(task_root)
        if requested_root.is_symlink():
            raise StorageError("task root must not be a symlink")
        self.task_root = requested_root.resolve(strict=True)
        if not self.task_root.is_dir():
            raise StorageError("task root must be a directory")
        requested = Path(reference_path)
        if requested.is_symlink():
            raise StorageError("reference input must not be a symlink")
        try:
            self.reference_path = requested.resolve(strict=True)
        except OSError as error:
            raise StorageError("reference input does not exist") from error
        if self.task_root not in self.reference_path.parents:
            raise StorageError("reference input must be inside task root")
        self._reject_symlink_components(requested)
        if not self.reference_path.is_file():
            raise StorageError("reference input must be a regular file")
        if isinstance(scene_threshold, bool) or not isinstance(scene_threshold, (int, float)):
            raise StorageError("scene threshold must be a number")
        if not 0 < float(scene_threshold) < 1:
            raise StorageError("scene threshold must be between zero and one")
        if timeout_seconds <= 0:
            raise StorageError("timeout must be positive")
        self.scene_threshold = float(scene_threshold)
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe = ffprobe or shutil.which("ffprobe") or "ffprobe"
        self.timeout_seconds = float(timeout_seconds)
        self._audio_present: bool | None = None

    def required_inputs(self) -> tuple[Path, ...]:
        return (self.reference_path,)

    def required_gates(self) -> tuple[str, ...]:
        return ()

    def declared_outputs(self) -> tuple[Path, ...]:
        outputs = [
            self.task_root / "recipe.json",
            self.task_root / "video_clips",
            self.task_root / "review_contact_sheet.jpg",
            self.task_root / "gate_review_packages/gate1.json",
        ]
        if self._source_has_audio():
            outputs.insert(2, self.task_root / "voice/reference-audio.m4a")
        return tuple(outputs)

    def cache_fingerprint(self) -> str:
        base = content_fingerprint(
            self.execution_stage_id,
            self.implementation_version,
            self.required_inputs(),
        )
        parameters = json.dumps(
            {"scene_threshold": self.scene_threshold}, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(f"{base}\0{parameters}".encode()).hexdigest()

    def execute(self, *, attempt_id: str) -> dict[str, object]:
        if not isinstance(attempt_id, str) or not _ATTEMPT_ID.fullmatch(attempt_id):
            raise StorageError("attempt_id is invalid")
        fingerprint = self.cache_fingerprint()
        if self._is_current(fingerprint):
            return self._result("cache_hit", attempt_id, fingerprint)
        existing = [path for path in self.declared_outputs() if path.exists() or path.is_symlink()]
        if existing:
            raise StorageError(f"reference split output already exists: {existing[0]}")
        staging = self.task_root / ".staging" / f"reference-split-{attempt_id}"
        if staging.exists() or staging.is_symlink():
            raise StorageError("reference split staging path already exists")
        promoted: list[Path] = []
        try:
            self._build(staging, fingerprint)
            promotions = [
                (staging / "video_clips", self.task_root / "video_clips"),
                (staging / "recipe.json", self.task_root / "recipe.json"),
                (staging / "review_contact_sheet.jpg", self.task_root / "review_contact_sheet.jpg"),
                (staging / "gate_review_packages/gate1.json", self.task_root / "gate_review_packages/gate1.json"),
            ]
            if (staging / "voice/reference-audio.m4a").is_file():
                promotions.insert(1, (staging / "voice/reference-audio.m4a", self.task_root / "voice/reference-audio.m4a"))
            for source, target in promotions:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, target)
                promoted.append(target)
        except BaseException:
            for path in reversed(promoted):
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                elif path.exists() and not path.is_symlink():
                    path.unlink()
            raise
        finally:
            if staging.exists() and not staging.is_symlink():
                shutil.rmtree(staging)
            staging_parent = staging.parent
            if staging_parent.is_dir() and not any(staging_parent.iterdir()):
                staging_parent.rmdir()
        return self._result("succeeded", attempt_id, fingerprint)

    def _build(self, staging: Path, fingerprint: str) -> None:
        clips = staging / "video_clips" / "shots"
        keyframes = staging / "video_clips" / "keyframes"
        clips.mkdir(parents=True)
        keyframes.mkdir(parents=True)
        (staging / "voice").mkdir(parents=True)
        probe = self._probe()
        duration = self._duration(probe)
        fps = self._fps(probe)
        cut_points = self._scene_cut_points(duration)
        boundaries = [0.0, *cut_points, duration]
        shots: list[dict[str, object]] = []
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), 1):
            clip_relative = f"video_clips/shots/shot{index:03d}.mp4"
            keyframe_relative = f"video_clips/keyframes/shot{index:03d}.jpg"
            self._extract_clip(start, end, staging / clip_relative)
            self._extract_keyframe((start + end) / 2, staging / keyframe_relative)
            shots.append(
                {
                    "shot_id": f"shot{index:03d}",
                    "start_seconds": round(start, 6),
                    "end_seconds": round(end, 6),
                    "duration_seconds": round(end - start, 6),
                    "start_frame": round(start * fps),
                    "end_frame": round(end * fps),
                    "clip_path": clip_relative,
                    "clip_sha256": self._sha256(staging / clip_relative),
                    "keyframe_path": keyframe_relative,
                    "keyframe_sha256": self._sha256(staging / keyframe_relative),
                    "review_status": "awaiting_user",
                }
            )
        contact = staging / "review_contact_sheet.jpg"
        self._contact_sheet(keyframes, contact, len(shots))
        streams = probe.get("streams", [])
        audio_stream = next(
            (row for row in streams if isinstance(row, dict) and row.get("codec_type") == "audio"),
            None,
        )
        if audio_stream is not None:
            self._extract_audio(staging / "voice/reference-audio.m4a")
        recipe: dict[str, Any] = {
            **_ENVELOPE,
            "input_fingerprint": fingerprint,
            "reference_video": {
                "path": self.reference_path.relative_to(self.task_root).as_posix(),
                "sha256": self._sha256(self.reference_path),
                "duration_seconds": round(duration, 6),
                "width": self._video_stream(probe).get("width"),
                "height": self._video_stream(probe).get("height"),
                "frame_rate": self._video_stream(probe).get("avg_frame_rate"),
                "streams": streams,
            },
            "scene_detection": {
                "algorithm": "ffmpeg-scene-score",
                "threshold": self.scene_threshold,
                "candidate_cut_points_seconds": [round(item, 6) for item in cut_points],
                "manual_revision": "awaiting_user",
            },
            "shots": shots,
            "audio": {
                "reference": {
                    "present": audio_stream is not None,
                    "path": "voice/reference-audio.m4a" if audio_stream is not None else None,
                    "sha256": self._sha256(staging / "voice/reference-audio.m4a") if audio_stream is not None else None,
                }
            },
        }
        atomic_write_json(staging / "recipe.json", recipe)
        atomic_write_json(
            staging / "gate_review_packages/gate1.json",
            {
                "gate_id": "gate1",
                "status": "awaiting_user",
                "input_fingerprint": fingerprint,
                "artifacts": {
                    "recipe.json": self._sha256(staging / "recipe.json"),
                    "review_contact_sheet.jpg": self._sha256(contact),
                },
                "shot_count": len(shots),
                "candidate_cut_points_seconds": recipe["scene_detection"]["candidate_cut_points_seconds"],
            },
        )

    def _probe(self) -> dict[str, Any]:
        completed = self._run(
            [self.ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(self.reference_path)]
        )
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise StorageError("ffprobe returned invalid JSON") from error
        if not isinstance(value, dict) or not isinstance(value.get("streams"), list):
            raise StorageError("ffprobe returned invalid media facts")
        self._video_stream(value)
        self._audio_present = any(
            isinstance(row, dict) and row.get("codec_type") == "audio"
            for row in value["streams"]
        )
        return value

    def _source_has_audio(self) -> bool:
        if self._audio_present is None:
            try:
                self._probe()
            except StorageError:
                return False
        return bool(self._audio_present)

    def _scene_cut_points(self, duration: float) -> list[float]:
        completed = self._run(
            [
                self.ffmpeg, "-hide_banner", "-loglevel", "info", "-i", str(self.reference_path),
                "-vf", f"select=gt(scene\\,{self.scene_threshold}),showinfo", "-an", "-f", "null", "-",
            ]
        )
        return sorted(
            {
                round(float(match), 6)
                for match in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", completed.stderr)
                if 0.001 < float(match) < duration - 0.001
            }
        )

    def _extract_clip(self, start: float, end: float, output: Path) -> None:
        self._run(
            [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.6f}",
                "-i", str(self.reference_path), "-t", f"{end - start:.6f}", "-map", "0:v:0",
                "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output),
            ]
        )

    def _extract_keyframe(self, timestamp: float, output: Path) -> None:
        self._run(
            [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.6f}",
                "-i", str(self.reference_path), "-frames:v", "1", "-q:v", "2", str(output),
            ]
        )

    def _extract_audio(self, output: Path) -> None:
        self._run(
            [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(self.reference_path), "-map", "0:a:0", "-vn",
                "-c:a", "aac", "-b:a", "128k", str(output),
            ]
        )

    def _contact_sheet(self, keyframes: Path, output: Path, count: int) -> None:
        columns = max(1, math.ceil(math.sqrt(count)))
        self._run(
            [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-framerate", "1",
                "-start_number", "1", "-i", str(keyframes / "shot%03d.jpg"), "-frames:v", "1",
                "-vf", f"scale=240:-1,tile={columns}x{math.ceil(count / columns)}", "-q:v", "2", str(output),
            ]
        )

    def _run(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                argv, check=True, capture_output=True, text=True, timeout=self.timeout_seconds
            )
        except FileNotFoundError as error:
            raise StorageError(f"required media tool is unavailable: {argv[0]}") from error
        except subprocess.TimeoutExpired as error:
            raise StorageError(f"media command timed out: {argv[0]}") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
            raise StorageError(f"media command failed: {detail[0]}") from error

    def _is_current(self, fingerprint: str) -> bool:
        if not all(path.exists() and not path.is_symlink() for path in self.declared_outputs()):
            return False
        try:
            recipe = read_json_object(self.task_root / "recipe.json")
        except StorageError:
            return False
        return recipe.get("input_fingerprint") == fingerprint

    def _reject_symlink_components(self, requested: Path) -> None:
        try:
            relative = requested.resolve(strict=True).relative_to(self.task_root)
        except ValueError as error:
            raise StorageError("reference input must be inside task root") from error
        current = self.task_root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise StorageError("reference input path must not contain symlinks")

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    @staticmethod
    def _video_stream(probe: dict[str, Any]) -> dict[str, Any]:
        for stream in probe.get("streams", []):
            if isinstance(stream, dict) and stream.get("codec_type") == "video":
                return stream
        raise StorageError("reference input has no video stream")

    @classmethod
    def _duration(cls, probe: dict[str, Any]) -> float:
        raw = probe.get("format", {}).get("duration")
        if raw is None:
            raw = cls._video_stream(probe).get("duration")
        try:
            duration = float(raw)
        except (TypeError, ValueError) as error:
            raise StorageError("reference duration is unavailable") from error
        if not math.isfinite(duration) or duration <= 0:
            raise StorageError("reference duration must be positive")
        return duration

    @classmethod
    def _fps(cls, probe: dict[str, Any]) -> float:
        raw = cls._video_stream(probe).get("avg_frame_rate") or "0/1"
        try:
            fps = float(Fraction(str(raw)))
        except (ValueError, ZeroDivisionError) as error:
            raise StorageError("reference frame rate is invalid") from error
        if not math.isfinite(fps) or fps <= 0:
            raise StorageError("reference frame rate must be positive")
        return fps

    def _result(self, status: str, attempt_id: str, fingerprint: str) -> dict[str, object]:
        return {
            "status": status,
            "attempt_id": attempt_id,
            "execution_stage_id": self.execution_stage_id,
            "implementation_version": self.implementation_version,
            "input_fingerprint": fingerprint,
            "stop_gate": self.stop_gate,
        }
