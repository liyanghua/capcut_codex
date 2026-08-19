"""Frozen tablemat inputs for repeatable G-B paired validation."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .measurement import MeasurementError
from .media_runtime import FFprobeDuration
from .storage import StorageError, atomic_write_json, read_json_object


_ENVELOPE = {
    "schema_version": "1.0.0",
    "contract_version": "2.0.0-alpha.1",
    "skill_version": "2.0.0-alpha.1",
}
CREATIVE_CONTRACT_VERSION = "creative_contract_v1"

_CLAIMS = (
    ("protect", "保护餐桌并保留木纹"),
    ("edge", "65度双斜切，圆润收边"),
    ("material", "进口冰晶粒，不含石蜡，抗UV更耐黄"),
    ("oil", "防油好擦"),
    ("flex", "柔韧铺平"),
    ("scratch", "防刮耐磨"),
    ("insurance", "一年发黄险，具体以保障条款为准"),
    ("care", "日常使用好打理"),
    ("close", "擦净以后使用更放心"),
)

_FRAGMENTS = (
    ("fragment01", "protect", "餐桌要保护。", "透明桌垫.mp4", "hook.protect", (), (0.1, 1.8)),
    ("fragment02", "protect", "木纹也要看见。", "7月16日.mp4", "hook.transparency", (), (1.8, 3.567)),
    ("fragment03", "edge", "65度双斜切，圆润收边。", "桌垫65度.jpg", "proof.edge", (), (0.0, 60.0)),
    ("fragment04", "material", "进口冰晶粒，不含石蜡，抗UV更耐黄。", "进口冰晶粒.jpg", "proof.material", (), (0.0, 60.0)),
    ("fragment05", "oil", "油污倒上去。", "7月16日.mp4", "proof.pour", ("pour",), (7.4, 8.8)),
    ("fragment06", "oil", "一擦就净。", "7月16日.mp4", "proof.wipe", ("wipe",), (8.8, 10.8)),
    ("fragment07", "flex", "柔韧，铺开更服帖。", "极简透明垫.mp4", "proof.flex", ("install",), (0.0, 2.448)),
    ("fragment08", "scratch", "日常防刮耐磨。", "透明桌垫.mp4", "proof.scratch", ("scratch",), (6.2, 8.6)),
    ("fragment09", "insurance", "还配一年发黄险，具体以保障条款为准。", "送发黄.jpg", "proof.insurance", (), (0.0, 60.0)),
    ("fragment10", "care", "铺好以后，日常使用都好打理。", "极简透明垫.mp4", "lifestyle.care", (), (9.0, 14.1)),
    ("fragment11", "close", "擦净以后，用着更放心。", "7月16日.mp4", "cta.close", ("wipe",), (10.2, 13.3)),
)


def prepare_tablemat_case(
    *, task_root: Path, reference_source: Path, asset_root: Path,
    creative_contract_version: str | None = None,
) -> dict[str, object]:
    task = Path(task_root).resolve(strict=False)
    if task.exists():
        raise ValueError("frozen task root must not exist")
    reference = Path(reference_source).resolve(strict=True)
    assets = Path(asset_root).resolve(strict=True)
    task.mkdir(parents=True)
    copied_reference = task / "reference-2026-08-16.mp4"
    shutil.copy2(reference, copied_reference)
    brief = {
        **_ENVELOPE,
        "artifact_type": "project_brief",
        "schema_id": "urn:capcut:remix-reference-video:artifact:project-brief",
        "approved_claims": [
            {"claim_id": claim_id, "text": text} for claim_id, text in _CLAIMS
        ],
        "approved_fallbacks": [],
        "forbidden_claims": ["2毫米厚度", "抗菌90%", "无味", "直边款", "各种桌型都适配"],
        "duration_envelope": {"minimum_seconds": 11, "maximum_seconds": 35, "strength": "soft"},
        "maximum_narration_chars_per_second": 5,
        "product": {"name": "透明餐桌垫", "audience": "普通家庭餐桌用户"},
        "target": {"platform": "抖音", "width": 1080, "height": 1920, "fps": 60},
        "voice": {"provider": "doubao", "credential_env": "DOUBAO_TTS_KEY"},
    }
    atomic_write_json(task / "project_brief.json", brief)
    atomic_write_json(task / "project_brief.yaml", brief)
    fragments: list[dict[str, object]] = []
    profiles: list[dict[str, object]] = []
    evidence: list[dict[str, object]] = []
    for fragment_id, claim_id, narration, source_name, semantic, actions, broad in _FRAGMENTS:
        source = (assets / source_name).resolve(strict=True)
        media_type = "image" if source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else "video"
        fragments.append({
            "fragment_id": fragment_id,
            "claim_ids": [claim_id],
            "narration": narration,
            "requirements": {
                "product_type": "tablemat",
                "required_semantics": [semantic],
                "required_actions": list(actions),
                "allowed_media_types": [media_type],
                "forbidden_semantics": [],
                "expected_visual_seconds": 0.5,
            },
        })
        digest = _sha256(source)
        profiles.append({
            "asset_id": f"{fragment_id}-asset",
            "source_id": source_name,
            "source_path": source_name,
            "sha256": digest,
            "perceptual_hash": hashlib.sha256(f"{digest}:{fragment_id}".encode()).hexdigest(),
            "product_type": "tablemat",
            "semantic_tags": [semantic],
            "action_tags": list(actions),
            "media_type": media_type,
            "overlay_detected": True,
            "duration_seconds": 60.0 if media_type == "image" else broad[1],
            "broad_ranges": [{"start_seconds": broad[0], "end_seconds": broad[1]}],
            "scores": {
                "semantic": 0.96, "action": 0.95, "composition": 0.91,
                "color": 0.90, "lighting": 0.90, "technical": 0.98,
            },
        })
        evidence.append({
            "fragment_id": fragment_id,
            "voice_text": narration,
            "approved_claim_ids": [claim_id],
            "selected_candidate_id": f"{fragment_id}-asset",
            "closure_decision": "closed_by_frozen_business_evidence",
        })
    atomic_write_json(task / "asset_profiles.json", {
        **_ENVELOPE,
        "artifact_type": "asset_profiles",
        "schema_id": "urn:capcut:remix-reference-video:artifact:asset-profiles",
        "asset_profiles": profiles,
    })
    stage_inputs = task / "stage_inputs"
    stage_inputs.mkdir()
    _handoff(stage_inputs / "compile-blueprint.json", "compile-blueprint", {"target_fragments": fragments})
    _handoff(stage_inputs / "compile-mutation-plan.json", "compile-mutation-plan", {"fallback_ids": []})
    _handoff(stage_inputs / "build-material-selection-package.json", "build-material-selection-package", {
        "overlay_decisions": {fragment_id: "retain_source_text" for fragment_id, *_ in _FRAGMENTS}
    })
    _handoff(stage_inputs / "validate-script-evidence.json", "validate-script-evidence", {"evidence_rows": evidence})
    snapshot = {
        "artifact_type": "g_b_frozen_input_snapshot",
        **_ENVELOPE,
        "schema_id": "urn:capcut:remix-reference-video:artifact:g-b-frozen-input-snapshot",
        "reference_sha256": _sha256(copied_reference),
        "brief_sha256": _sha256(task / "project_brief.json"),
        "asset_profiles_sha256": _sha256(task / "asset_profiles.json"),
        "asset_snapshot": {source_name: _sha256(assets / source_name) for _, _, _, source_name, *_ in _FRAGMENTS},
        "approval_records": [],
    }
    if creative_contract_version is not None:
        if creative_contract_version != CREATIVE_CONTRACT_VERSION:
            raise ValueError(f"unsupported creative contract version: {creative_contract_version}")
        snapshot["creative_contract_version"] = CREATIVE_CONTRACT_VERSION
    atomic_write_json(task / "g_b_frozen_input_snapshot.json", snapshot)
    return snapshot


def validate_frozen_input(
    *, frozen_root: Path, asset_root: Path
) -> dict[str, object]:
    """Validate the immutable source snapshot used by a G-B pair.

    Only source inputs are accepted here.  Existing pipeline state, decisions,
    review packages and rendered media are deliberately ignored and never
    become pair inputs.
    """

    requested_root = Path(frozen_root)
    if requested_root.is_symlink():
        raise MeasurementError("frozen input root must be a regular directory")
    root = requested_root.resolve(strict=True)
    if not root.is_dir():
        raise MeasurementError("frozen input root must be a regular directory")
    marker_path = root / "g_b_frozen_input_snapshot.json"
    try:
        marker = read_json_object(marker_path)
    except StorageError as error:
        raise MeasurementError("g_b_frozen_input_snapshot.json is required") from error
    if marker.get("artifact_type") != "g_b_frozen_input_snapshot":
        raise MeasurementError("g_b_frozen_input_snapshot.json is required")
    reference_candidates = sorted(root.glob("reference-*.mp4"))
    if len(reference_candidates) != 1:
        raise MeasurementError("frozen input must contain exactly one reference-*.mp4")
    reference = reference_candidates[0]
    brief = root / "project_brief.json"
    profiles = root / "asset_profiles.json"
    for path, label in ((brief, "project_brief.json"), (profiles, "asset_profiles.json")):
        if not path.is_file() or path.is_symlink():
            raise MeasurementError(f"frozen input is missing {label}")
    expected_reference = marker.get("reference_sha256")
    expected_brief = marker.get("brief_sha256")
    expected_profiles = marker.get("asset_profiles_sha256")
    if expected_reference != _sha256(reference):
        raise MeasurementError("frozen reference hash does not match snapshot")
    if expected_brief != _sha256(brief):
        raise MeasurementError("frozen brief hash does not match snapshot")
    if expected_profiles != _sha256(profiles):
        raise MeasurementError("frozen asset profile hash does not match snapshot")
    sources = marker.get("asset_snapshot")
    if not isinstance(sources, dict) or not sources:
        raise MeasurementError("frozen asset snapshot is empty")
    requested_assets = Path(asset_root)
    if requested_assets.is_symlink():
        raise MeasurementError("asset root must be a regular directory")
    assets = requested_assets.resolve(strict=True)
    if not assets.is_dir():
        raise MeasurementError("asset root must be a regular directory")
    for name, expected in sources.items():
        if not isinstance(name, str) or Path(name).name != name:
            raise MeasurementError("frozen asset names must be direct children")
        source = assets / name
        if source.is_symlink() or not source.is_file():
            raise MeasurementError(f"frozen asset is missing: {name}")
        if expected != _sha256(source):
            raise MeasurementError(f"frozen asset hash does not match: {name}")
    return {
        "reference_path": reference,
        "brief_path": brief,
        "asset_profiles_path": profiles,
        "asset_root": assets,
        "asset_snapshot": dict(sources),
        "snapshot_sha256": _sha256(marker_path),
    }


def prepare_frozen_pair(
    *, frozen_root: Path, cold_root: Path, hot_root: Path, asset_root: Path
) -> dict[str, object]:
    """Create clean pair roots from frozen inputs without copying decisions."""

    inputs = validate_frozen_input(frozen_root=frozen_root, asset_root=asset_root)
    cold = Path(cold_root).resolve(strict=False)
    hot = Path(hot_root).resolve(strict=False)
    if cold.exists() or hot.exists():
        raise MeasurementError("cold and hot task roots must not already exist")
    if cold == hot or cold in hot.parents or hot in cold.parents:
        raise MeasurementError("cold and hot task roots must be separate")
    for destination in (cold, hot):
        destination.mkdir(parents=True)
        for name in ("reference_path", "brief_path", "asset_profiles_path"):
            source = Path(inputs[name])
            shutil.copy2(source, destination / source.name)
        for source in Path(frozen_root).glob("project_brief.yaml"):
            shutil.copy2(source, destination / source.name)
        source_handoffs = Path(frozen_root) / "stage_inputs"
        if source_handoffs.is_dir():
            shutil.copytree(source_handoffs, destination / "stage_inputs")
        atomic_write_json(destination / "g_b_frozen_input_snapshot.json", {
            **read_json_object(Path(frozen_root) / "g_b_frozen_input_snapshot.json"),
            "pair_role": "cold" if destination == cold else "hot",
            "approval_records": [],
        })
        (destination / "cache").mkdir()
    return {
        "cold_task_root": str(cold),
        "hot_task_root": str(hot),
        "snapshot_sha256": inputs["snapshot_sha256"],
        "approval_reuse": False,
        "copied_task_artifacts": False,
    }


def clone_declared_cold_cache(*, cold_root: Path, hot_root: Path) -> dict[str, object]:
    """Copy only the cold run's declared cache directory into the hot run."""

    cold = Path(cold_root).resolve(strict=True)
    hot = Path(hot_root).resolve(strict=True)
    source = cold / "cache"
    destination = hot / "cache"
    if not source.is_dir() or source.is_symlink():
        raise MeasurementError("cold cache directory is missing")
    if not destination.is_dir() or destination.is_symlink():
        raise MeasurementError("hot cache destination must be empty")

    source_files = _cache_file_inventory(source)
    destination_files = _cache_file_inventory(destination)
    if destination_files:
        if destination_files == source_files:
            return {
                "status": "reused",
                "source": "cold/cache",
                "destination": "hot/cache",
                "file_count": sum(value != "<directory>" for value in destination_files.values()),
            }
        raise MeasurementError("hot cache destination does not match cold cache")

    for child in source.iterdir():
        if child.is_symlink():
            raise MeasurementError("cache symlinks are not allowed")
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        elif child.is_file():
            shutil.copy2(child, target)
        else:
            raise MeasurementError("cold cache contains unsupported entry")
    return {
        "status": "cloned",
        "source": "cold/cache",
        "destination": "hot/cache",
        "file_count": sum(1 for path in destination.rglob("*") if path.is_file()),
    }


def reuse_existing_hot_cache(*, cold_root: Path, hot_root: Path) -> dict[str, object]:
    """Preserve a hot cache that has already been used by the hot runner.

    The asset index intentionally updates per-run scan metadata. Once hot has
    a committed pipeline state, byte-for-byte comparison with cold would reject
    that legitimate local increment and make resume impossible.
    """

    cold = Path(cold_root).resolve(strict=True)
    hot = Path(hot_root).resolve(strict=True)
    source = cold / "cache"
    destination = hot / "cache"
    if not source.is_dir() or source.is_symlink():
        raise MeasurementError("cold cache directory is missing")
    if not destination.is_dir() or destination.is_symlink():
        raise MeasurementError("hot cache destination is missing")
    inventory = _cache_file_inventory(destination)
    file_count = sum(value != "<directory>" for value in inventory.values())
    if file_count == 0:
        raise MeasurementError("hot cache destination is empty")
    return {
        "status": "preserved",
        "source": "cold/cache",
        "destination": "hot/cache",
        "file_count": file_count,
    }


def _cache_file_inventory(root: Path) -> dict[str, str]:
    """Return a strict relative-path to SHA-256 inventory for a cache tree."""

    inventory: dict[str, str] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise MeasurementError("cache symlinks are not allowed")
        if path.is_dir():
            inventory[relative] = "<directory>"
            continue
        if not path.is_file():
            raise MeasurementError("cache contains unsupported entry")
        inventory[relative] = _sha256(path)
    return inventory


def refresh_candidate_source_durations(
    *, candidate_path: Path, asset_root: Path
) -> dict[str, float]:
    """Replace frozen-fixture duration caps with measured source durations.

    This only corrects the derived ``available_source_range`` before Gate 3
    approval.  It does not change selected candidates or approved ranges.
    """

    candidate = read_json_object(candidate_path)
    selections = candidate.get("selections")
    if candidate.get("artifact_type") != "material_selection_candidate" or not isinstance(selections, list):
        raise MeasurementError("material selection candidate is required")
    assets = Path(asset_root).resolve(strict=True)
    duration = FFprobeDuration()
    measured: dict[str, float] = {}
    for row in selections:
        if not isinstance(row, dict) or row.get("media_type") != "video":
            continue
        fragment_id, source_path = row.get("fragment_id"), row.get("source_path")
        if not isinstance(fragment_id, str) or not isinstance(source_path, str):
            raise MeasurementError("video selection identity is invalid")
        source = (assets / source_path).resolve(strict=True)
        if assets not in source.parents or source.is_symlink():
            raise MeasurementError("candidate source escapes asset root")
        actual = round(float(duration(source)), 6)
        available = row.get("available_source_range")
        if not isinstance(available, dict):
            raise MeasurementError(f"available source range is missing: {fragment_id}")
        start = available.get("start_seconds", 0.0)
        if isinstance(start, bool) or not isinstance(start, (int, float)):
            raise MeasurementError(f"available source range is invalid: {fragment_id}")
        available["end_seconds"] = actual
        measured[fragment_id] = actual
    atomic_write_json(candidate_path, candidate)
    return measured


def write_pair_measurement(
    *, pair_root: Path, cold: dict[str, object], hot: dict[str, object], status: str,
    reason: str | None = None,
) -> Path:
    """Persist a conservative pair evidence envelope for later review."""

    root = Path(pair_root).resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        **_ENVELOPE,
        "artifact_type": "g_b_pair_measurement",
        "schema_id": "urn:capcut:remix-reference-video:artifact:g-b-pair-measurement",
        "status": status,
        "created_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "cold": cold,
        "hot": hot,
        "v1_comparability": {"status": "not_measured", "reason": "no real V1 baseline in this pair"},
        "g_b_thresholds": {"status": "not_measured", "reason": reason or "fresh Gate 5 approvals and timing evidence are required"},
    }
    path = root / "gb_measurement.json"
    atomic_write_json(path, payload)
    return path


def _handoff(path: Path, stage_id: str, payload: dict[str, object]) -> None:
    atomic_write_json(path, {
        **_ENVELOPE,
        "artifact_type": "stage_input",
        "schema_id": "urn:capcut:remix-reference-video:artifact:stage-input",
        "stage_id": stage_id,
        "producer": "g-b-frozen-case-v1",
        "created_at": "2026-08-16T00:00:00Z",
        "lifecycle_status": "awaiting_user",
        "input_hashes": {},
        "payload": payload,
    })


def _sha256(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


__all__ = [
    "prepare_tablemat_case",
    "validate_frozen_input",
    "prepare_frozen_pair",
    "clone_declared_cold_cache",
    "reuse_existing_hot_cache",
    "refresh_candidate_source_durations",
    "write_pair_measurement",
]
