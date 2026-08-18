from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from remix_reference_video.storage import atomic_write_json


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_frozen_run_fixture(task: Path, *, pair_role: str = "cold") -> None:
    reference = task / "reference-fixture.mp4"
    reference.write_bytes(b"reference-fixture")
    brief = task / "project_brief.json"
    atomic_write_json(brief, {"artifact_type": "project_brief"})
    profiles = task / "asset_profiles.json"
    atomic_write_json(profiles, {"artifact_type": "asset_profiles"})
    assets = task / "fixture-assets"
    assets.mkdir(exist_ok=True)
    asset = assets / "asset.mp4"
    asset.write_bytes(b"asset-fixture")
    client = task / "tts_client.py"
    client.write_text("# fixture\n", encoding="utf-8")
    (task / "cache").mkdir(exist_ok=True)
    atomic_write_json(
        task / "g_b_frozen_input_snapshot.json",
        {
            "artifact_type": "g_b_frozen_input_snapshot",
            "pair_role": pair_role,
            "reference_sha256": _sha256(reference),
            "brief_sha256": _sha256(brief),
            "asset_profiles_sha256": _sha256(profiles),
            "asset_snapshot": {asset.name: _sha256(asset)},
            "approval_records": [],
        },
    )
    atomic_write_json(
        task / "production_runtime_config.json",
        {
            "artifact_type": "production_runtime_config",
            "reference_path": reference.name,
            "asset_root": assets.name,
            "brief_path": brief.name,
            "asset_profiles_path": profiles.name,
            "cache_path": "cache/assets.sqlite3",
            "doubao_client_script": client.name,
            "python_executable": sys.executable,
        },
    )
