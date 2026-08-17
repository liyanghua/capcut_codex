#!/usr/bin/env python3
"""Minimal Track A static guardrail; never creates production media or changes state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = ROOT / ".agents" / "skills" / "remix-reference-video"
DOCS = [
    ROOT / "AGENTS.md",
    ROOT / "docs" / "reference-video-remix-optimization-plan.md",
    ROOT / "docs" / "reference-video-remix-sop.md",
    SKILL_ROOT / "SKILL.md",
    *sorted((SKILL_ROOT / "references").glob("*.md")),
]
EXPECTED_SKILL_VERSION = "2.0.0-alpha.1"
EXPECTED_CONTRACT_VERSION = "2.0.0-alpha.1"
EXPECTED_ARTIFACT_SCHEMA_VERSION = "1.0.0"
EXPECTED_ACTIVE_ARTIFACTS = {
    "project_brief",
    "pipeline_state",
    "recipe",
    "shot_blueprint",
    "content_baseline",
    "mutation_plan",
    "coverage_precheck",
    "coverage_report",
    "asset_profiles",
    "matches",
    "fragment_plan",
    "script_evidence_matrix",
    "production_script_candidate",
    "approved_production_script",
    "material_manifest",
    "voice_preflight",
    "voice_script",
    "voice_manifest",
    "duration_report",
    "voice_qa_report",
    "reconstruction_timeline",
    "match_validation_report",
    "material_validation_report",
    "final_validation_report",
    "render_report",
    "jianying_import_manifest",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def load_yaml_with_ruby(path: Path) -> dict:
    script = (
        'require "json"; require "yaml"; '
        'data = YAML.safe_load(File.read(ARGV[0]), permitted_classes: [], aliases: false); '
        'STDOUT.write(JSON.generate(data))'
    )
    result = subprocess.run(
        ["ruby", "-e", script, str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"YAML parse failed for {path.relative_to(ROOT)}: {result.stderr.strip()}")
    parsed = json.loads(result.stdout)
    if not isinstance(parsed, dict):
        fail(f"YAML root must be a mapping: {path.relative_to(ROOT)}")
    return parsed


def validate_v2_metadata(data: dict, artifact_type: str, schema_id: str, label: str) -> None:
    expected = {
        "artifact_type": artifact_type,
        "schema_id": schema_id,
        "schema_version": EXPECTED_ARTIFACT_SCHEMA_VERSION,
        "contract_version": EXPECTED_CONTRACT_VERSION,
        "skill_version": EXPECTED_SKILL_VERSION,
    }
    for key, value in expected.items():
        if data.get(key) != value:
            fail(f"{label} {key} mismatch: expected {value!r}, got {data.get(key)!r}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        help="Read an alternate registry file for validation without changing the Skill package.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest_path = SKILL_ROOT / "manifest.json"
    if not manifest_path.is_file():
        fail("manifest.json is missing")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("name") != "remix-reference-video":
        fail("manifest name mismatch")
    if manifest.get("version") != EXPECTED_SKILL_VERSION:
        fail("Track A must use version 2.0.0-alpha.1")
    if manifest.get("manifest_schema_version") != "1.0.0":
        fail("manifest schema version must be 1.0.0")
    if manifest.get("contract_version") != EXPECTED_CONTRACT_VERSION:
        fail("manifest contract version mismatch")
    if manifest.get("rollback_skill_version") != "1.0.0":
        fail("rollback version must remain 1.0.0")
    if manifest.get("tracks", {}).get("track_b") != "locked_until_g_a":
        fail("Track B is not locked until G-A")
    if manifest.get("tracks", {}).get("track_c") != "locked_until_g_b":
        fail("Track C is not locked until G-B")
    if manifest.get("contract_compatibility", {}).get("v2_production_enabled") is not False:
        fail("ordinary V2 production must remain disabled until G-A")
    expected_pilot_policy = {
        "maximum_active_pilots": 1,
        "production_release": False,
        "archive_allowed": False,
        "approval_reuse_allowed": False,
        "requires_gate_stop": True,
    }
    if manifest.get("pilot_policy") != expected_pilot_policy:
        fail("manifest pilot policy must enforce one non-production, non-archivable pilot")

    registry_path = args.registry or (SKILL_ROOT / manifest.get("schema_registry_path", ""))
    if not registry_path.is_file():
        fail("canonical schema registry is missing")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if registry.get("registry_version") != manifest.get("schema_registry_version"):
        fail("manifest and registry version mismatch")
    if registry.get("x-skill") != {"name": manifest["name"], "version": manifest["version"]}:
        fail("manifest and registry skill identity mismatch")
    contract = registry.get("x-contracts", {}).get("v2_alpha", {})
    if contract.get("contract_version") != EXPECTED_CONTRACT_VERSION:
        fail("registry contract version mismatch")
    if contract.get("default_artifact_schema_version") != EXPECTED_ARTIFACT_SCHEMA_VERSION:
        fail("registry artifact schema version mismatch")
    if contract.get("full_shape_validator") not in {"deferred_to_track_b", "snapshot_schema_validator"}:
        fail("registry full shape validator declaration is invalid")

    artifacts = registry.get("x-artifacts")
    if not isinstance(artifacts, list):
        fail("registry x-artifacts must be a list")
    track_a_artifacts = [item for item in artifacts if item.get("track", "A") == "A"]
    active_types = {item.get("artifact_type") for item in track_a_artifacts if item.get("status") == "active"}
    if active_types != EXPECTED_ACTIVE_ARTIFACTS:
        missing_types = sorted(EXPECTED_ACTIVE_ARTIFACTS - active_types)
        extra_types = sorted(active_types - EXPECTED_ACTIVE_ARTIFACTS)
        fail(f"registry artifact set mismatch; missing={missing_types}, extra={extra_types}")
    paths = [item.get("path") for item in artifacts]
    schema_ids = [item.get("schema_id") for item in artifacts]
    if len(paths) != len(set(paths)):
        fail("registry artifact paths must be unique")
    if len(schema_ids) != len(set(schema_ids)):
        fail("registry artifact schema IDs must be unique")
    if any(item.get("track") not in {"A", "B"} for item in artifacts):
        fail("registry artifacts must declare Track A or Track B")
    registered_pairs = {
        (item.get("artifact_type"), item.get("schema_id"))
        for item in track_a_artifacts
        if item.get("status") == "active"
    }
    schema_pairs = set()
    for branch in registry.get("oneOf", []):
        properties = branch.get("properties", {})
        artifact_type = properties.get("artifact_type", {}).get("const")
        schema_id = properties.get("schema_id", {}).get("const")
        if (artifact_type in EXPECTED_ACTIVE_ARTIFACTS or artifact_type == "stage_input") and schema_id:
            schema_pairs.add((artifact_type, schema_id))
    handoff = registry.get("x-stage-input-contract", {})
    handoff_pair = (handoff.get("artifact_type"), handoff.get("schema_id"))
    expected_schema_pairs = registered_pairs | {handoff_pair}
    if schema_pairs != expected_schema_pairs:
        fail("registry oneOf type/schema ID bindings must exactly match active artifacts")

    brief_path = SKILL_ROOT / "assets" / "project_brief.yaml"
    brief = load_yaml_with_ruby(brief_path)
    validate_v2_metadata(
        brief,
        "project_brief",
        "urn:capcut:remix-reference-video:artifact:project-brief",
        "project brief template",
    )
    if "workflow_contract" in brief or "contract_version" in brief.get("review", {}):
        fail("project brief contains a duplicate contract alias")

    fixture_path = SKILL_ROOT / "trigger_smoke_cases.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if fixture.get("fixture_schema_version") != "1.0.0":
        fail("trigger fixture schema version mismatch")
    if fixture.get("skill") != manifest["name"] or fixture.get("skill_version") != manifest["version"]:
        fail("trigger fixture skill identity mismatch")
    if fixture.get("contract_version") != manifest["contract_version"]:
        fail("trigger fixture contract version mismatch")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not 12 <= len(cases) <= 15:
        fail("trigger fixture must contain 12-15 cases")
    valid_expectations = {"should_trigger", "should_not_trigger", "near_neighbor"}
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)) or any(not case_id for case_id in ids):
        fail("trigger fixture IDs must be non-empty and unique")
    if any(case.get("expect") not in valid_expectations or not case.get("prompt") for case in cases):
        fail("trigger fixture has an invalid expectation or empty prompt")

    missing = [str(path.relative_to(ROOT)) for path in DOCS if not path.is_file()]
    if missing:
        fail(f"missing migration files: {', '.join(missing)}")

    text = "\n".join(path.read_text(encoding="utf-8") for path in DOCS)
    primary_text = "\n".join(path.read_text(encoding="utf-8") for path in DOCS[:3])
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    ref_text = "\n".join(path.read_text(encoding="utf-8") for path in (SKILL_ROOT / "references").glob("*.md"))
    required = {
        "gate3 split": "gate3_material_selection" in primary_text and "gate3_evidence_closure" in primary_text and "gate3_material_selection" in skill_text,
        "gate4 split": "gate4_pre_generation" in primary_text and "gate4_post_generation" in primary_text and "gate4_pre_generation" in ref_text,
        "broad plan": "approved_broad_range" in text and "reconstruction_timeline.json" in text,
        "request omit": "request_omit" in text and ("返回 Gate 2" in text or "返回 **Gate 2**" in text),
        "recipe boundary": "V2 不在 `recipe.json` 写入真实替换配音时长" in text,
        "approved script": "approved_production_script.json" in text,
        "voice projection": "source_approved_script_sha256" in text and "只读执行投影" in text,
        "validation reports split": all(name in text for name in ("match_validation_report.json", "material_validation_report.json", "final_validation_report.json")),
        "pilot never archives": "pilot 即使 Gate 5 批准也永久留在 `work/`" in text,
        "gate3 approved inputs": all(name in text for name in ("content_baseline.json", "mutation_plan.json", "coverage_report.json")),
        "v2 decisions authority": "V2 审批只写入 `decisions[]`" in text,
    }
    for label, ok in required.items():
        if not ok:
            fail(f"required contract marker missing: {label}")

    forbidden = [
        r"Gate 3 批准后才写生产计划",
        r"Gate 3 直接批准删段",
        r"Gate 1–4 均为 `approved`",
    ]
    for pattern in forbidden:
        if re.search(pattern, text):
            fail(f"legacy rule remains: {pattern}")

    secret_pattern = re.compile(r"(?i)(api[_-]?key|access[_-]?token)\s*[:=]\s*[\"'][^\"']+[\"']")
    for path in DOCS + [manifest_path]:
        if secret_pattern.search(path.read_text(encoding="utf-8")):
            fail(f"possible credential literal in {path.relative_to(ROOT)}")

    openai_yaml = load_yaml_with_ruby(SKILL_ROOT / "agents" / "openai.yaml")
    interface = openai_yaml.get("interface")
    if not isinstance(interface, dict):
        fail("openai.yaml interface must be a mapping")
    for field in ("display_name", "short_description", "default_prompt"):
        if not isinstance(interface.get(field), str) or not interface[field].strip():
            fail(f"openai.yaml interface.{field} is missing")

    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    print("PASS: Track A static contract checks")
    print(f"manifest_sha256={manifest_hash}")
    print(f"checked_files={len(DOCS) + 5}")
    print("registry_envelope=passed")
    print("brief_yaml_parse=passed")
    print("openai_yaml_parse=passed")
    print("trigger_fixture_structure=passed")
    print("trigger_behavior_evaluation=not_run")
    print("full_artifact_shape_validation=deferred_to_track_b")
    print("production_media_comparison=not_run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
