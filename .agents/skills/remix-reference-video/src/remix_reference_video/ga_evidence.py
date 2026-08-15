"""Temporary, manual-only evidence harness for the pre-G-A pilot."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .storage import StorageError, TaskStorage, atomic_write_json, read_json_object

_GATES = (
    "gate1",
    "gate2",
    "gate3_material_selection",
    "gate3_evidence_closure",
    "gate4_pre_generation",
    "gate4_post_generation",
    "gate5",
)
_DECISIONS = {"approved", "rejected", "partial"}
_STRUCTURAL = {"request_omit", "request_merge", "request_restructure"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _root(task_dir: Path) -> Path:
    root = Path(task_dir).resolve(strict=True)
    if not root.is_dir():
        raise StorageError(f"task directory is not a directory: {root}")
    return root


def _relative_file(root: Path, value: str) -> tuple[str, Path]:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise StorageError("artifact path must be a non-empty relative path")
    relative = Path(value)
    candidate = root / relative
    if candidate.is_symlink():
        raise StorageError(f"artifact must not be a symlink: {value}")
    resolved = candidate.resolve(strict=False)
    if root != resolved and root not in resolved.parents:
        raise StorageError(f"artifact path escapes task root: {value}")
    if resolved.is_symlink() or not resolved.is_file():
        raise StorageError(f"artifact must be an existing regular file: {value}")
    return relative.as_posix(), resolved


def prepare_review(task_dir: Path, gate_id: str, artifacts: list[str]) -> dict[str, Any]:
    root = _root(task_dir)
    if gate_id not in _GATES:
        raise StorageError(f"unsupported G-A gate: {gate_id}")
    state = read_json_object(root / "pipeline_state.json")
    if state.get("execution_mode") != "manual-contract-only":
        raise StorageError("WP-A2 only accepts manual-contract-only tasks")
    if not artifacts:
        raise StorageError("at least one artifact is required")
    input_hashes: dict[str, str] = {}
    for item in artifacts:
        relative, path = _relative_file(root, item)
        if relative in input_hashes:
            raise StorageError(f"duplicate artifact: {relative}")
        input_hashes[relative] = _hash(path)
    package = {
        "artifact_type": "ga_review_package",
        "schema_id": "remix-reference-video/ga-review-package",
        "schema_version": "1.0.0",
        "gate_id": gate_id,
        "run_id": state.get("run_id"),
        "execution_mode": "manual-contract-only",
        "created_at": _now(),
        "input_hashes": input_hashes,
    }
    package_path = root / "gate_review_packages" / f"{gate_id}.json"
    atomic_write_json(package_path, package)
    return {**package, "package_path": package_path.relative_to(root).as_posix()}


def record_decision(
    task_dir: Path,
    gate_id: str,
    review_package: str,
    decision_file: str,
    actor: str,
) -> dict[str, Any]:
    root = _root(task_dir)
    state = read_json_object(root / "pipeline_state.json")
    if state.get("execution_mode") != "manual-contract-only":
        raise StorageError("WP-A2 only accepts manual-contract-only tasks")
    package_rel, package_path = _relative_file(root, review_package)
    package = read_json_object(package_path)
    if package.get("gate_id") != gate_id or package.get("execution_mode") != "manual-contract-only":
        raise StorageError("review package does not match gate or execution mode")
    if package.get("run_id") != state.get("run_id"):
        raise StorageError("review package belongs to a different pilot run")
    hashes = package.get("input_hashes")
    if not isinstance(hashes, dict) or not hashes:
        raise StorageError("review package has no input hashes")
    for relative, expected in hashes.items():
        _, path = _relative_file(root, relative)
        if _hash(path) != expected:
            raise StorageError(f"review package input hash mismatch: {relative}")
    decision_rel, decision_path = _relative_file(root, decision_file)
    raw = read_json_object(decision_path)
    decision = raw.get("decision")
    if decision not in _DECISIONS:
        raise StorageError("decision must be approved, rejected, or partial")
    if not isinstance(actor, str) or not actor.strip():
        raise StorageError("actor is required")
    scope_type = raw.get("scope_type")
    scope_ids = raw.get("scope_ids")
    if not isinstance(scope_type, str) or not isinstance(scope_ids, list) or not scope_ids:
        raise StorageError("scope_type and non-empty scope_ids are required")
    directives = raw.get("directives", {})
    if not isinstance(directives, dict):
        raise StorageError("directives must be an object")
    if gate_id.startswith("gate3") and any(key in _STRUCTURAL for key in directives):
        raise StorageError("Gate 3 cannot approve structural changes; return to Gate 2")
    existing = state.get("decisions", [])
    if not isinstance(existing, list):
        raise StorageError("pipeline_state.decisions must be an array")
    if any(isinstance(item, dict) and item.get("gate_id") == gate_id and item.get("status") not in {"revoked", "stale", "superseded"} for item in existing):
        raise StorageError(f"active decision already exists for {gate_id}")
    if decision == "approved":
        predecessor_requirements = {
            "gate2": ("gate1",),
            "gate3_material_selection": ("gate1", "gate2"),
            "gate3_evidence_closure": ("gate1", "gate2", "gate3_material_selection"),
            "gate4_pre_generation": ("gate1", "gate2", "gate3_material_selection", "gate3_evidence_closure"),
            "gate4_post_generation": ("gate1", "gate2", "gate3_material_selection", "gate3_evidence_closure", "gate4_pre_generation"),
            "gate5": ("gate1", "gate2", "gate3_material_selection", "gate3_evidence_closure", "gate4_pre_generation", "gate4_post_generation"),
        }
        active_approved = {item.get("gate_id") for item in existing if isinstance(item, dict) and item.get("decision") == "approved" and item.get("status") not in {"revoked", "stale", "superseded"}}
        missing = [required for required in predecessor_requirements.get(gate_id, ()) if required not in active_approved]
        if missing:
            raise StorageError(f"cannot approve {gate_id} before: {', '.join(missing)}")
    timestamp = _now()
    entry = {
        "decision_id": f"ga-{gate_id}-{len(existing) + 1}",
        "gate_id": gate_id,
        "decision": decision,
        "scope_type": scope_type,
        "scope_ids": scope_ids,
        "directives": directives,
        "actor": actor.strip(),
        "approved_at": timestamp,
        "review_package": package_rel,
        "input_hashes": hashes,
        "status": "active",
        "decision_file": decision_rel,
    }
    store = TaskStorage(root)
    updated = store.update_state(lambda current: _apply_decision(current, gate_id, decision, entry))
    store.append_event({"event_type": "ga.decision.recorded", "gate_id": gate_id, "decision_id": entry["decision_id"]}, state_revision=updated["state_revision"])
    return {"status": "recorded", **entry, "state_revision": updated["state_revision"]}


def _apply_decision(state: dict[str, Any], gate_id: str, decision: str, entry: dict[str, Any]) -> dict[str, Any]:
    gates = state.setdefault("gate_status", {})
    if not isinstance(gates, dict):
        raise StorageError("pipeline_state.gate_status must be an object")
    gates[gate_id] = "approved" if decision == "approved" else ("blocked" if decision == "rejected" else "awaiting_user")
    state.setdefault("decisions", []).append(entry)
    return state


def audit_ga(task_dir: Path) -> dict[str, Any]:
    """Read-only G-A audit; never creates a control file or repairs state."""
    root = _root(task_dir)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        state = read_json_object(root / "pipeline_state.json")
    except StorageError as error:
        return {"status": "failed", "errors": [str(error)], "warnings": []}
    if state.get("execution_mode") != "manual-contract-only":
        errors.append("WP-A2 only accepts manual-contract-only tasks")
    decisions = state.get("decisions", [])
    if not isinstance(decisions, list):
        errors.append("pipeline_state.decisions must be an array")
        decisions = []
    package_entries: dict[str, dict[str, Any]] = {}
    packages_dir = root / "gate_review_packages"
    if packages_dir.exists() and not packages_dir.is_dir():
        errors.append("gate_review_packages must be a directory")
    elif packages_dir.is_dir():
        for package_path in packages_dir.glob("*.json"):
            if package_path.is_symlink():
                errors.append(f"review package must not be a symlink: {package_path.name}")
                continue
            try:
                package = read_json_object(package_path)
                gate = package.get("gate_id")
                if gate not in _GATES:
                    errors.append(f"unsupported review package gate: {gate}")
                else:
                    package_entries[gate] = package
                    for relative, expected in (package.get("input_hashes") or {}).items():
                        _, path = _relative_file(root, relative)
                        if _hash(path) != expected:
                            errors.append(f"hash mismatch for {relative} ({gate})")
            except (StorageError, TypeError):
                errors.append(f"invalid review package: {package_path.name}")
    seen: set[str] = set()
    approved: set[str] = set()
    for item in decisions:
        if not isinstance(item, dict):
            errors.append("decision must be an object")
            continue
        gate = item.get("gate_id")
        if not isinstance(gate, str) or gate not in _GATES:
            errors.append("decision has unsupported gate")
            continue
        if gate in seen and item.get("status") not in {"revoked", "stale", "superseded"}:
            errors.append(f"duplicate active decision for {gate}")
        if item.get("status") not in {"revoked", "stale", "superseded"}:
            seen.add(gate)
        if item.get("decision") == "approved":
            approved.add(gate)
        package_rel = item.get("review_package")
        try:
            _, package_path = _relative_file(root, package_rel)
            package = read_json_object(package_path)
            if package.get("created_at") and item.get("approved_at") and package["created_at"] > item["approved_at"]:
                errors.append(f"approval precedes review package for {gate}")
            for relative, expected in (package.get("input_hashes") or {}).items():
                _, path = _relative_file(root, relative)
                if _hash(path) != expected:
                    errors.append(f"hash mismatch for {relative} ({gate})")
        except (StorageError, TypeError):
            errors.append(f"invalid or missing review package for {gate}")
        if gate.startswith("gate3") and any(key in _STRUCTURAL for key in (item.get("directives") or {})):
            errors.append(f"structural change recorded at {gate}; must return to gate2")
    for gate in package_entries:
        if not any(isinstance(item, dict) and item.get("gate_id") == gate for item in decisions):
            warnings.append(f"review package has no recorded decision: {gate}")
    order = [gate for gate in _GATES if gate in approved]
    for earlier, later in zip(order, order[1:]):
        if _GATES.index(later) > _GATES.index(earlier) + 1 and later != "gate5":
            warnings.append(f"gate order has unapproved predecessor before {later}")
    status = "failed" if errors else ("passed_with_warnings" if warnings else "passed")
    ga_ready = not errors and all(gate in approved for gate in _GATES)
    return {
        "status": status,
        "ga_ready": ga_ready,
        "execution_mode": state.get("execution_mode"),
        "run_id": state.get("run_id"),
        "errors": errors,
        "warnings": warnings,
        "approved_gates": order,
    }
