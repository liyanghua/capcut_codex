#!/usr/bin/env python3
"""Small, dependency-free Doubao Speech 2.0 CLI adapter for the remix Skill."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from urllib import request as urlrequest


SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/tts/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/tts/query"


class DoubaoClientError(RuntimeError):
    pass


def request_headers(resource_id: str, request_id: str) -> dict[str, str]:
    key = os.environ.get("DOUBAO_SPEECH_API_KEY", "").strip()
    if not key:
        raise DoubaoClientError("Doubao credential is missing")
    return {
        "X-Api-Key": key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": request_id,
        "Content-Type": "application/json",
    }


def submit_body(*, text: str, voice: str, sample_rate: int, speech_rate: int, request_id: str) -> dict[str, object]:
    return {
        "user": {"uid": "remix-reference-video"},
        "unique_id": request_id,
        "req_params": {
            "text": text,
            "speaker": voice,
            "audio_params": {"format": "mp3", "sample_rate": sample_rate, "speech_rate": speech_rate, "enable_timestamp": True},
            "additions": json.dumps({"disable_markdown_filter": False}, ensure_ascii=False),
        },
    }


def _post(url: str, headers: dict[str, str], payload: dict[str, object], timeout: float) -> dict[str, object]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urlrequest.Request(url, data=body, headers=headers, method="POST")
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise DoubaoClientError(f"Doubao request failed: {error}") from error
    if result.get("code") != 20000000:
        raise DoubaoClientError(f"Doubao request rejected: {result.get('message', 'unknown error')}")
    return result


def synthesize(*, text: str, output: Path, resource_id: str, voice: str, sample_rate: int, speech_rate: int, timeout_seconds: int) -> None:
    if not text.strip():
        raise DoubaoClientError("text is required")
    request_id = str(uuid.uuid4())
    headers = request_headers(resource_id, request_id)
    submit = _post(SUBMIT_URL, headers, submit_body(text=text, voice=voice, sample_rate=sample_rate, speech_rate=speech_rate, request_id=request_id), 60)
    task_id = (submit.get("data") or {}).get("task_id")
    if not task_id:
        raise DoubaoClientError("Doubao submit returned no task id")
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        time.sleep(2)
        query = _post(QUERY_URL, request_headers(resource_id, str(uuid.uuid4())), {"task_id": task_id}, 60)
        data = query.get("data") or {}
        status = data.get("task_status")
        if status == 2:
            audio_url = data.get("audio_url")
            if not audio_url:
                raise DoubaoClientError("Doubao returned no audio URL")
            output.parent.mkdir(parents=True, exist_ok=True)
            urlrequest.urlretrieve(str(audio_url), output)
            if not output.is_file() or output.stat().st_size == 0:
                raise DoubaoClientError("Doubao returned an empty audio file")
            return
        if status == 3:
            raise DoubaoClientError("Doubao task failed")
    raise DoubaoClientError("Doubao task timed out")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--endpoint", default=SUBMIT_URL)
    parser.add_argument("--resource-id", default="seed-tts-2.0")
    parser.add_argument("--voice", default=os.environ.get("DOUBAO_SPEECH_VOICE_TYPE", "zh_female_gaolengyujie_uranus_bigtts"))
    parser.add_argument("--sample-rate", type=int, default=24000)
    parser.add_argument("--speech-rate", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()
    try:
        synthesize(text=args.text, output=args.output, resource_id=args.resource_id, voice=args.voice, sample_rate=args.sample_rate, speech_rate=args.speech_rate, timeout_seconds=args.timeout_seconds)
    except DoubaoClientError as error:
        print(str(error), file=__import__("sys").stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
