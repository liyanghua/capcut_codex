"""Frozen-pair isolation and minimal Phase 6 G-B measurement snapshots."""

from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path


class MeasurementError(ValueError):
    pass


class FrozenPairHarness:
    @staticmethod
    def assert_empty_cold_cache(cache_root: Path) -> None:
        root = Path(cache_root).resolve(strict=True)
        if not root.is_dir() or any(root.iterdir()):
            raise MeasurementError("empty cold cache is required")

    @staticmethod
    def clone_hot_cache(*, cold_cache: Path, hot_cache: Path) -> None:
        source = Path(cold_cache).resolve(strict=True)
        destination = Path(hot_cache).resolve(strict=False)
        if not source.is_dir():
            raise MeasurementError("cold result cache must be a directory")
        if destination.exists() and any(destination.iterdir()):
            raise MeasurementError("hot cache destination must be empty")
        if destination.exists():
            destination.rmdir()
        shutil.copytree(source, destination)

    @staticmethod
    def validate_controlled_mutation(
        base_inputs: Mapping[str, object],
        mutated_inputs: Mapping[str, object],
        allowed_fields: set[str],
    ) -> None:
        changed = {
            key
            for key in set(base_inputs) | set(mutated_inputs)
            if base_inputs.get(key) != mutated_inputs.get(key)
        }
        unexpected = changed - allowed_fields
        if unexpected:
            raise MeasurementError(
                f"uncontrolled mutation: {', '.join(sorted(unexpected))}"
            )

    @staticmethod
    def validate_separate_approvals(
        first: Mapping[str, object], second: Mapping[str, object]
    ) -> None:
        if first.get("run_id") == second.get("run_id"):
            raise MeasurementError("paired runs must have separate run ids")
        first_ids = set(first.get("decision_ids", []))
        second_ids = set(second.get("decision_ids", []))
        if first_ids.intersection(second_ids):
            raise MeasurementError("approval reuse is forbidden across paired runs")

    @staticmethod
    def validate_cache_reads(
        paths: Sequence[Path], *, allowed_cache_root: Path
    ) -> None:
        root = Path(allowed_cache_root).resolve(strict=True)
        for path in paths:
            resolved = Path(path).resolve(strict=False)
            if resolved != root and root not in resolved.parents:
                raise MeasurementError("cross-run cache read is forbidden")


class Phase6Snapshot:
    STAGES = (
        "performance_proven_video",
        "blueprint",
        "controlled_mutation",
        "retrieval",
        "reconstruction",
    )
    _METRICS = (
        "machine_api_critical_path_seconds",
        "human_wait_seconds",
        "operator_touch_seconds",
        "rework_seconds",
        "gate_return_count",
    )

    def build(
        self,
        *,
        stage_scores: Mapping[str, object],
        metrics: Mapping[str, object],
        cache_status: str,
        v1_metrics: Mapping[str, object] | None,
    ) -> dict[str, object]:
        if set(stage_scores) != set(self.STAGES):
            raise MeasurementError("exactly five framework stage scores are required")
        scores: dict[str, float] = {}
        for stage in self.STAGES:
            value = stage_scores[stage]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
                raise MeasurementError(f"invalid stage score: {stage}")
            scores[stage] = float(value)
        measured: dict[str, float | int] = {}
        for name in self._METRICS:
            value = metrics.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise MeasurementError(f"invalid metric: {name}")
            measured[name] = value
        if cache_status not in {"cold", "hot", "controlled_mutation"}:
            raise MeasurementError("cache status is invalid")
        if v1_metrics is None or any(
            not isinstance(v1_metrics.get(name), (int, float))
            for name in ("rework_seconds", "gate_return_count")
        ):
            raise MeasurementError("V1 comparability data is required")
        overall = round(sum(scores.values()) / len(scores), 2)
        critical_limit = 780 if cache_status == "cold" else 480
        thresholds_met = (
            all(value >= 88 for value in scores.values())
            and overall >= 88
            and float(measured["machine_api_critical_path_seconds"]) <= critical_limit
            and float(measured["rework_seconds"]) <= float(v1_metrics["rework_seconds"])
            and float(measured["gate_return_count"]) <= float(v1_metrics["gate_return_count"])
        )
        return {
            "artifact_type": "phase6_score_snapshot",
            "schema_version": "1.0.0",
            "measurement_status": "measured",
            "framework_stage_scores": scores,
            "video_quality_score": overall,
            "minimum_video_quality_score": 88,
            "target_video_quality_score": 91,
            **measured,
            "cache_status": cache_status,
            "critical_path_limit_seconds": critical_limit,
            "human_wait_excluded_from_machine_path": True,
            "g_b_thresholds_met": thresholds_met,
            "owner_g_b_approval_required": True,
        }
