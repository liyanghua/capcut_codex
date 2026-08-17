"""Validation and derivation of G-B forward-baseline policy status."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class BaselinePolicyError(ValueError):
    pass


class BaselinePolicy:
    def __init__(self, value: Mapping[str, Any]) -> None:
        required = ("policy_id", "policy_version", "require_v1_comparability", "allowed_not_evaluated_metrics", "frozen_input_sha256")
        missing = [key for key in required if key not in value]
        if missing:
            raise BaselinePolicyError(f"missing policy fields: {', '.join(missing)}")
        if not isinstance(value["require_v1_comparability"], bool):
            raise BaselinePolicyError("require_v1_comparability must be boolean")
        self.value = dict(value)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BaselinePolicy":
        if "baseline_status" in value:
            raise BaselinePolicyError("baseline_status is derived, not caller supplied")
        return cls(value)

    def compare(self, *, frozen_snapshot_sha256: str, run_role: str, prior_snapshot: Mapping[str, Any] | None = None, prior_snapshot_sha256: str | None = None) -> dict[str, Any]:
        expected = self.value["frozen_input_sha256"]
        checks: dict[str, dict[str, Any]] = {}
        valid = True
        if frozen_snapshot_sha256 != expected:
            valid = False
            checks["frozen_input"] = {"status": "fail", "reason": "frozen input hash mismatch", "threshold": expected}
        else:
            checks["frozen_input"] = {"status": "pass", "reason": "frozen input hash matches", "threshold": expected}
        if run_role not in {"cold", "hot"}:
            valid = False
            checks["run_role"] = {"status": "fail", "reason": "run role must be cold or hot"}
        else:
            checks["run_role"] = {"status": "pass", "reason": "run role accepted"}
        if prior_snapshot is None:
            status = "establishing" if valid else "invalid"
        else:
            if prior_snapshot.get("policy_id") != self.value["policy_id"] or prior_snapshot.get("policy_version") != self.value["policy_version"] or (prior_snapshot_sha256 and prior_snapshot_sha256 != prior_snapshot.get("snapshot_sha256")):
                valid = False
            status = "established" if valid else "invalid"
        return {"policy_id": self.value["policy_id"], "policy_version": self.value["policy_version"], "baseline_status": status, "checks": checks, "require_v1_comparability": self.value["require_v1_comparability"], "allowed_not_evaluated_metrics": list(self.value["allowed_not_evaluated_metrics"])}

    @staticmethod
    def frozen_input_hash(path: Path) -> str:
        return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
