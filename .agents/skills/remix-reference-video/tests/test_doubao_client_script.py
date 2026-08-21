from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from remix_reference_video.cli import _load_workspace_env


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "doubao_tts_client.py"


def _load_client():
    spec = importlib.util.spec_from_file_location("doubao_tts_client", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Doubao client")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DoubaoClientScriptTests(unittest.TestCase):
    def test_workspace_env_loader_sets_missing_values_without_overriding_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"EXISTING_ENV": "process"}, clear=False):
            root = Path(temporary)
            (root / ".env").write_text("NEW_ENV=loaded\nEXISTING_ENV=file\n", encoding="utf-8")
            os.environ.pop("NEW_ENV", None)
            _load_workspace_env(root)
            self.assertEqual(os.environ["NEW_ENV"], "loaded")
            self.assertEqual(os.environ["EXISTING_ENV"], "process")
            os.environ.pop("NEW_ENV", None)

    def test_request_contract_uses_environment_secret_without_serializing_it(self) -> None:
        client = _load_client()
        with patch.dict(os.environ, {"DOUBAO_SPEECH_API_KEY": "secret-value"}, clear=False):
            headers = client.request_headers("seed-tts-2.0", "request-1")
            body = client.submit_body(
                text="透明桌垫防水防油",
                voice="zh_female_gaolengyujie_uranus_bigtts",
                sample_rate=24000,
                speech_rate=0,
                request_id="request-1",
            )
        self.assertEqual(headers["X-Api-Key"], "secret-value")
        self.assertEqual(body["req_params"]["speaker"], "zh_female_gaolengyujie_uranus_bigtts")
        self.assertNotIn("secret-value", repr(body))

    def test_cli_requires_output_and_never_creates_it_without_a_key(self) -> None:
        client = _load_client()
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"DOUBAO_SPEECH_API_KEY": "", "DOUBAO_TTS_KEY": ""}, clear=False
        ):
            output = Path(temporary) / "voice.mp3"
            with self.assertRaisesRegex(client.DoubaoClientError, "credential"):
                client.synthesize(
                    text="测试", output=output, resource_id="seed-tts-2.0",
                    voice="zh_female_gaolengyujie_uranus_bigtts", sample_rate=24000,
                    speech_rate=0, timeout_seconds=1,
                )
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
