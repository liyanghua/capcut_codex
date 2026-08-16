from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from remix_reference_video.storage import atomic_write_json
from remix_reference_video.voice import (
    DoubaoV3Provider,
    RetryableVoiceError,
    VoiceError,
    VoiceGenerator,
)


class RecordingProvider:
    provider_id = "doubao-v3"

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    def synthesize(self, **kwargs: object) -> bytes:
        self.calls.append(dict(kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return bytes(outcome)


class VoiceGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name).resolve()
        self.script = self.root / "approved_production_script.json"
        atomic_write_json(
            self.script,
            {
                "artifact_type": "approved_production_script",
                "lines": [
                    {"fragment_id": "fragment01", "text": "第一句"},
                    {"fragment_id": "fragment02", "text": "第二句"},
                ],
                "tts_settings": {"voice": "female", "speed_ratio": 1.0},
            },
        )

    def test_uses_only_approved_script_and_stable_idempotency_keys(self) -> None:
        provider = RecordingProvider([b"audio-1", b"audio-2"])
        generator = VoiceGenerator(provider, audio_validator=lambda value: bool(value))
        first = generator.generate(self.script, self.root / "voice")
        second = generator.generate(self.script, self.root / "voice")

        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(provider.calls[0]["timeout_seconds"], 60.0)
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])
        self.assertEqual(first["provider_id"], "doubao-v3")
        draft = self.root / "production_script_candidate.json"
        atomic_write_json(draft, {"artifact_type": "production_script_candidate", "lines": []})
        with self.assertRaisesRegex(VoiceError, "approved_production_script"):
            generator.generate(draft, self.root / "other-voice")

    def test_retries_only_retryable_categories_with_capped_backoff(self) -> None:
        provider = RecordingProvider(
            [
                RetryableVoiceError("timeout"),
                RetryableVoiceError("rate_limit", retry_after_seconds=99),
                b"audio-1",
                b"audio-2",
            ]
        )
        waits: list[float] = []
        manifest = VoiceGenerator(
            provider,
            sleep=waits.append,
            audio_validator=lambda value: bool(value),
        ).generate(self.script, self.root / "voice")

        self.assertEqual(len(provider.calls), 4)
        self.assertEqual(waits, [2.0, 60.0])
        self.assertEqual(manifest["attempt_count"], 4)

    def test_three_attempt_limit_and_incomplete_audio_rejection(self) -> None:
        provider = RecordingProvider([RetryableVoiceError("server_5xx")] * 3)
        with self.assertRaisesRegex(VoiceError, "after 3 attempts"):
            VoiceGenerator(provider, sleep=lambda _: None).generate(
                self.script, self.root / "voice"
            )
        invalid = RecordingProvider([b"partial"])
        with self.assertRaisesRegex(VoiceError, "incomplete audio"):
            VoiceGenerator(invalid, audio_validator=lambda value: False).generate(
                self.script, self.root / "invalid-voice"
            )
        self.assertFalse((self.root / "invalid-voice/final_voice.bin").exists())

    def test_doubao_provider_invokes_client_without_secret_argument(self) -> None:
        client = self.root / "client.py"
        client.write_text(
            "import argparse, pathlib\n"
            "p=argparse.ArgumentParser(); p.add_argument('--text'); p.add_argument('--output'); "
            "p.add_argument('--endpoint'); p.add_argument('--resource-id'); p.add_argument('--voice'); "
            "p.add_argument('--sample-rate'); a=p.parse_args(); pathlib.Path(a.output).write_bytes(b'ID3-real')\n",
            encoding="utf-8",
        )
        provider = DoubaoV3Provider(
            client_script=client, python_executable=sys.executable
        )
        with patch.dict(os.environ, {"DOUBAO_TTS_KEY": "top-secret"}, clear=False):
            audio = provider.synthesize(
                text="测试",
                settings={"speaker": "voice-1"},
                timeout_seconds=5,
                idempotency_key="key-1",
            )
        self.assertEqual(audio, b"ID3-real")
        self.assertNotIn("top-secret", provider.last_command)

    def test_voice_generator_uses_provider_extension_and_combiner(self) -> None:
        class Provider:
            provider_id = "mp3-provider"
            audio_extension = ".mp3"

            def synthesize(self, **kwargs: object) -> bytes:
                return f"audio:{kwargs['text']}".encode()

            def combine_audio(self, chunks: list[bytes]) -> bytes:
                return b"combined:" + b"|".join(chunks)

        manifest = VoiceGenerator(Provider()).generate(
            self.script, self.root / "combined-voice"
        )
        self.assertEqual(
            manifest["segments"][0]["path"], "segment-01-fragment01.mp3"
        )
        self.assertEqual(manifest["final_voice"]["path"], "final_voice.mp3")
        self.assertEqual(
            (self.root / "combined-voice" / "final_voice.mp3").read_bytes(),
            b"combined:audio:\xe7\xac\xac\xe4\xb8\x80\xe5\x8f\xa5|audio:\xe7\xac\xac\xe4\xba\x8c\xe5\x8f\xa5",
        )


if __name__ == "__main__":
    unittest.main()
