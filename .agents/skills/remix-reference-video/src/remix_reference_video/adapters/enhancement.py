"""Isolated, operator-triggered shot enhancement candidates."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


class EnhancementAdapter:
    implementation_version = "enhancement-adapter-v1"

    def __init__(self, task_root: Path) -> None:
        self.root = Path(task_root).resolve()

    def propose(self, *, shot_id: str, objective_id: str, source_materials: list[Path], modification_intent: str) -> dict[str, object]:
        if not shot_id or not source_materials or not modification_intent:
            raise ValueError("shot_id, source_materials and modification_intent are required")
        candidate_dir = self.root / "enhancement_candidates" / shot_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        candidates = []
        for index, source in enumerate(source_materials[:3], 1):
            source = Path(source).resolve(strict=True)
            candidate_id = f"enh-{shot_id}-{index}"
            target = candidate_dir / f"{candidate_id}{source.suffix or '.bin'}"
            shutil.copy2(source, target)
            candidates.append({"candidate_id": candidate_id, "path": target.relative_to(self.root).as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "status": "candidate"})
        return {"artifact_type": "enhancement_plan", "schema_id": "urn:capcut:remix-reference-video:artifact:enhancement-plan", "schema_version": "1.0.0", "contract_version": "2.0.0-alpha.1", "skill_version": "2.0.0-alpha.1", "implementation_version": self.implementation_version, "lifecycle_status": "ready", "input_hashes": {path.name: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in source_materials}, "status": "ready", "shot_id": shot_id, "objective_id": objective_id, "modification_intent": modification_intent, "source_material_ids": [path.name for path in source_materials], "provider": "stub", "model": "copy-isolated-v1", "prompt_template_version": "enhancement_prompt_v1", "candidates": candidates, "failure_reason": None}

    def adopt(self, candidate_id: str, plan: dict[str, object]) -> dict[str, object]:
        candidates = plan.get("candidates", [])
        if not any(isinstance(row, dict) and row.get("candidate_id") == candidate_id for row in candidates if isinstance(candidates, list)):
            raise ValueError("enhancement candidate is not allowlisted")
        return {"candidate_id": candidate_id, "earliest_recovery_gate": "gate3_material_selection", "stale_gates": ["gate3_material_selection", "gate3_evidence_closure", "gate3", "gate4_pre_generation", "gate4_post_generation", "gate4", "gate5"], "requires_manual_gate3_selection": True}
