"""Deterministic multi-strategy reference decomposition."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence


STRATEGIES = (
    "structure_semantic_v1",
    "rhythm_visual_v1",
    "evidence_action_v1",
    "hybrid_commerce_v1",
)


class DecompositionAdapter:
    implementation_version = "decomposition-adapter-v1"

    def build(
        self,
        recipe: Mapping[str, object],
        *,
        requested_strategies: Sequence[str] | None = None,
    ) -> dict[str, object]:
        shots = recipe.get("shots", [])
        shots = shots if isinstance(shots, list) else []
        requested = list(requested_strategies or ("hybrid_commerce_v1",))
        if not 1 <= len(requested) <= 3 or any(item not in STRATEGIES for item in requested):
            raise ValueError("requested decomposition strategies must contain 1-3 known strategy ids")
        candidates = []
        for strategy_id in requested:
            rows = []
            for index, shot in enumerate(shots):
                if not isinstance(shot, Mapping):
                    continue
                shot_id = str(shot.get("shot_id") or f"shot-{index + 1}")
                rows.append({
                    "segment_id": f"{strategy_id}:{shot_id}",
                    "reference_shot_id": shot_id,
                    "semantic_role": self._role(strategy_id, shot, index, len(shots)),
                    "required_actions": list(shot.get("required_actions", [])) if isinstance(shot.get("required_actions"), list) else [],
                    "hook": index == 0,
                    "rhythm_peak": strategy_id == "rhythm_visual_v1" and index in {0, max(0, len(shots) // 2)},
                    "confidence": 1.0 if shot.get("semantic") or shot.get("narrative_role") else 0.7,
                })
            canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            candidates.append({
                "decomposition_id": hashlib.sha256(f"{strategy_id}:{canonical}".encode()).hexdigest()[:16],
                "strategy_id": strategy_id,
                "implementation_version": self.implementation_version,
                "reference_shot_ids": [row["reference_shot_id"] for row in rows],
                "segments": rows,
                "low_confidence_items": [row["segment_id"] for row in rows if float(row["confidence"]) < 0.8],
                "input_hashes": {"recipe.json": hashlib.sha256(canonical.encode()).hexdigest()},
            })
        return {"implementation_version": self.implementation_version, "candidates": candidates}

    @staticmethod
    def _role(strategy_id: str, shot: Mapping[str, object], index: int, total: int) -> str:
        if strategy_id == "structure_semantic_v1":
            return str(shot.get("narrative_role") or ("opening" if index == 0 else "close" if index == total - 1 else "context"))
        if strategy_id == "rhythm_visual_v1":
            return "rhythm_peak" if index in {0, max(0, total // 2)} else "transition"
        if strategy_id == "evidence_action_v1":
            return "proof" if shot.get("required_actions") else "context"
        return "opening" if index == 0 else "close" if index == total - 1 else ("proof" if shot.get("required_actions") else "context")
