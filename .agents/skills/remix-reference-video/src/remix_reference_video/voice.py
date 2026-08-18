"""Idempotent, bounded-retry voice generation from an approved script."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from .storage import atomic_write_json, read_json_object


class VoiceError(RuntimeError):
    pass


class RetryableVoiceError(RuntimeError):
    def __init__(
        self, category: str, *, retry_after_seconds: float | None = None
    ) -> None:
        super().__init__(category)
        self.category = category
        self.retry_after_seconds = retry_after_seconds


class VoiceProvider(Protocol):
    provider_id: str

    def synthesize(self, **kwargs: object) -> bytes: ...


class DoubaoV3Provider:
    """Call the audited V3 WebSocket client without exposing its credential."""

    provider_id = "doubao-v3"
    audio_extension = ".mp3"

    def __init__(
        self,
        *,
        client_script: Path,
        python_executable: str = sys.executable,
        ffmpeg_executable: str = "ffmpeg",
    ) -> None:
        self.client_script = Path(client_script).resolve(strict=True)
        self.python_executable = python_executable
        self.ffmpeg_executable = ffmpeg_executable
        self.last_command: tuple[str, ...] = ()

    def synthesize(self, **kwargs: object) -> bytes:
        text = kwargs.get("text")
        settings = kwargs.get("settings")
        timeout = kwargs.get("timeout_seconds", 60.0)
        if not isinstance(text, str) or not text:
            raise VoiceError("Doubao text is required")
        if not isinstance(settings, Mapping):
            raise VoiceError("Doubao settings are required")
        if not os.environ.get("DOUBAO_TTS_KEY", "").strip():
            raise VoiceError("DOUBAO_TTS_KEY is missing")
        speaker = str(
            settings.get("speaker")
            or settings.get("voice")
            or settings.get("voice_type")
            or "zh_female_gaolengyujie_uranus_bigtts"
        )
        endpoint = str(
            settings.get("endpoint")
            or "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
        )
        resource_id = str(settings.get("resource_id") or "seed-tts-2.0")
        sample_rate = str(settings.get("sample_rate") or 24000)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "voice.mp3"
            command = (
                self.python_executable,
                str(self.client_script),
                "--text",
                text,
                "--output",
                str(output),
                "--endpoint",
                endpoint,
                "--resource-id",
                resource_id,
                "--voice",
                speaker,
                "--sample-rate",
                sample_rate,
            )
            self.last_command = command
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.client_script.parent,
                    capture_output=True,
                    text=True,
                    timeout=float(timeout),
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise TimeoutError("Doubao TTS timed out") from error
            if completed.returncode != 0 or not output.is_file():
                detail = (completed.stderr or completed.stdout or "Doubao TTS failed")[:800]
                raise VoiceError(detail.replace(os.environ["DOUBAO_TTS_KEY"], "[REDACTED]"))
            return output.read_bytes()

    def combine_audio(self, chunks: list[bytes]) -> bytes:
        if not chunks:
            raise VoiceError("audio chunks are required")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs: list[str] = []
            for index, chunk in enumerate(chunks, 1):
                path = root / f"segment-{index:02d}.mp3"
                path.write_bytes(chunk)
                inputs.extend(("-i", str(path)))
            output = root / "combined.mp3"
            filters = "".join(f"[{index}:a]" for index in range(len(chunks)))
            command = (
                self.ffmpeg_executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                *inputs,
                "-filter_complex",
                f"{filters}concat=n={len(chunks)}:v=0:a=1[outa]",
                "-map",
                "[outa]",
                "-c:a",
                "libmp3lame",
                "-ar",
                "44100",
                "-ac",
                "2",
                str(output),
            )
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            if completed.returncode != 0 or not output.is_file():
                raise VoiceError((completed.stderr or "FFmpeg audio concat failed")[:800])
            return output.read_bytes()


_RETRYABLE = frozenset({"timeout", "connection", "rate_limit", "server_5xx"})


class VoiceGenerator:
    def __init__(
        self,
        provider: VoiceProvider,
        *,
        sleep: Callable[[float], None] = time.sleep,
        audio_validator: Callable[[bytes], bool] | None = None,
    ) -> None:
        if not isinstance(provider.provider_id, str) or not provider.provider_id:
            raise VoiceError("provider_id is required")
        self.provider = provider
        self.sleep = sleep
        self.audio_validator = audio_validator or bool

    def generate(self, approved_script_path: Path, output_dir: Path) -> dict[str, object]:
        script_path = Path(approved_script_path)
        if script_path.is_symlink() or script_path.suffix != ".json":
            raise VoiceError("TTS input must be an approved production script JSON")
        script = read_json_object(script_path.resolve(strict=True))
        if script.get("artifact_type") != "approved_production_script":
            raise VoiceError("TTS input must be approved_production_script")
        lines = script.get("lines")
        settings = script.get("tts_settings")
        if not isinstance(lines, list) or not lines or not isinstance(settings, Mapping):
            raise VoiceError("approved script lines and tts_settings are required")
        script_hash = self._sha256(script_path)
        key_payload = {
            "provider_id": self.provider.provider_id,
            "script_sha256": script_hash,
            "tts_settings": dict(settings),
        }
        idempotency_key = hashlib.sha256(
            json.dumps(key_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        output = Path(output_dir)
        extension = getattr(self.provider, "audio_extension", ".bin")
        if not isinstance(extension, str) or not extension.startswith("."):
            raise VoiceError("provider audio_extension is invalid")
        final_name = f"final_voice{extension}"
        manifest_path = output / "voice_manifest.json"
        if manifest_path.is_file() and not manifest_path.is_symlink():
            cached = read_json_object(manifest_path)
            if cached.get("idempotency_key") == idempotency_key and all(
                (output / str(item.get("path"))).is_file()
                for item in cached.get("segments", [])
                if isinstance(item, Mapping)
            ) and (output / final_name).is_file():
                return cached
        generated: list[tuple[str, bytes, int]] = []
        total_attempts = 0
        for index, row in enumerate(lines, 1):
            if not isinstance(row, Mapping):
                raise VoiceError("approved script line is invalid")
            fragment_id, text = row.get("fragment_id"), row.get("text")
            if not isinstance(fragment_id, str) or not isinstance(text, str) or not text:
                raise VoiceError("approved script line needs fragment_id and text")
            segment_key = hashlib.sha256(
                f"{idempotency_key}:{fragment_id}:{index}".encode()
            ).hexdigest()
            audio: bytes | None = None
            for attempt in range(1, 4):
                total_attempts += 1
                try:
                    audio = self.provider.synthesize(
                        text=text,
                        settings=dict(settings),
                        timeout_seconds=60.0,
                        idempotency_key=segment_key,
                    )
                    break
                except TimeoutError as error:
                    retryable = RetryableVoiceError("timeout")
                    if attempt == 3:
                        raise VoiceError("voice generation failed after 3 attempts") from error
                    self.sleep(2.0 ** attempt)
                except RetryableVoiceError as error:
                    if error.category not in _RETRYABLE:
                        raise VoiceError(f"voice generation is not retryable: {error.category}") from error
                    if attempt == 3:
                        raise VoiceError("voice generation failed after 3 attempts") from error
                    delay = (
                        min(max(float(error.retry_after_seconds or 0), 0.0), 60.0)
                        if error.category == "rate_limit"
                        else min(2.0 ** attempt, 60.0)
                    )
                    self.sleep(delay)
            if audio is None or not isinstance(audio, bytes) or not self.audio_validator(audio):
                raise VoiceError(f"incomplete audio for {fragment_id}")
            generated.append((fragment_id, audio, index))
        output.mkdir(parents=True, exist_ok=True)
        segment_rows: list[dict[str, object]] = []
        chunks = [audio for _, audio, _ in generated]
        combiner = getattr(self.provider, "combine_audio", None)
        final = combiner(chunks) if callable(combiner) else b"".join(chunks)
        for fragment_id, audio, index in generated:
            name = f"segment-{index:02d}-{fragment_id}{extension}"
            self._atomic_bytes(output / name, audio)
            segment_rows.append(
                {"fragment_id": fragment_id, "path": name, "sha256": hashlib.sha256(audio).hexdigest()}
            )
        self._atomic_bytes(output / final_name, final)
        manifest = {
            "artifact_type": "voice_manifest",
            "provider_id": self.provider.provider_id,
            "source_approved_script_path": script_path.name,
            "source_approved_script_sha256": script_hash,
            "idempotency_key": idempotency_key,
            "attempt_count": total_attempts,
            "ai_generated": True,
            "segments": segment_rows,
            "final_voice": {
                "path": final_name,
                "sha256": hashlib.sha256(final).hexdigest(),
            },
        }
        atomic_write_json(manifest_path, manifest)
        return manifest

    @staticmethod
    def _atomic_bytes(path: Path, payload: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
