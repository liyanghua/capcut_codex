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
        stage_scores: Mapping[str, object] | None = None,
        metrics: Mapping[str, object] | None = None,
        cache_status: str | None = None,
        v1_metrics: Mapping[str, object] | None = None,
        run_id: str | None = None,
        state_revision: int | None = None,
        framework_stages: Sequence[Mapping[str, object]] | None = None,
        process_assessment: Mapping[str, object] | None = None,
        baseline_result: Mapping[str, object] | None = None,
        input_hashes: Mapping[str, str] | None = None,
        lifecycle_status: str = "measured",
        supersedes_snapshot_id: str | None = None,
    ) -> dict[str, object]:
        if framework_stages is not None:
            return self._build_evidence_bound(
                run_id=run_id,
                state_revision=state_revision,
                framework_stages=framework_stages,
                process_assessment=process_assessment or {},
                baseline_result=baseline_result or {},
                input_hashes=input_hashes or {},
                lifecycle_status=lifecycle_status,
                supersedes_snapshot_id=supersedes_snapshot_id,
            )
        if stage_scores is None or metrics is None or cache_status is None:
            raise MeasurementError("legacy stage_scores, metrics, and cache_status are required")
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

    def _build_evidence_bound(
        self,
        *,
        run_id: str | None,
        state_revision: int | None,
        framework_stages: Sequence[Mapping[str, object]],
        process_assessment: Mapping[str, object],
        baseline_result: Mapping[str, object],
        input_hashes: Mapping[str, str],
        lifecycle_status: str,
        supersedes_snapshot_id: str | None,
    ) -> dict[str, object]:
        if not isinstance(run_id, str) or not run_id:
            raise MeasurementError("run_id is required")
        if len(framework_stages) != len(self.STAGES):
            raise MeasurementError("exactly five framework stages are required")
        rows: list[dict[str, object]] = []
        scores: list[float] = []
        for expected, raw in zip(self.STAGES, framework_stages):
            if raw.get("framework_stage_id") != expected:
                raise MeasurementError("framework stages must use canonical order")
            items = raw.get("rubric_items")
            status = raw.get("measurement_status")
            if not isinstance(items, list):
                raise MeasurementError(f"{expected} rubric_items must be an array")
            valid = True
            earned = max_points = 0.0
            for item in items:
                if not isinstance(item, Mapping) or not isinstance(item.get("rubric_id"), str) or not isinstance(item.get("evidence_paths"), list) or not item.get("evidence_paths") or not isinstance(item.get("reason"), str) or not item.get("reason"):
                    valid = False; continue
                ep, mp = item.get("earned_points"), item.get("max_points")
                if isinstance(ep, bool) or not isinstance(ep, (int, float)) or isinstance(mp, bool) or not isinstance(mp, (int, float)) or mp <= 0 or ep < 0 or ep > mp:
                    valid = False; continue
                earned += float(ep); max_points += float(mp)
            if status == "measured" and valid and max_points > 0:
                score = round(earned / max_points * 100, 2); scores.append(score)
                stage_status = "measured"
            else:
                score = None; stage_status = "not_scored"
            rows.append({**dict(raw), "framework_stage_id": expected, "stage_output_quality_score": score, "measurement_status": stage_status})
        quality = round(sum(scores) / len(scores), 2) if len(scores) == 5 else None
        metrics = process_assessment.get("metrics") if isinstance(process_assessment.get("metrics"), Mapping) else {}
        critical = metrics.get("machine_api_critical_path_seconds", {}) if isinstance(metrics, Mapping) else {}
        critical_value = critical.get("value") if isinstance(critical, Mapping) else None
        thresholds_not_evaluated = ["rework_seconds", "gate_return_count"] if baseline_result.get("require_v1_comparability") is False and baseline_result.get("baseline_status") == "establishing" else []
        limit = 780 if baseline_result.get("run_role", "cold") == "cold" else 480
        thresholds = quality is not None and quality >= 88 and all(row["stage_output_quality_score"] is not None and float(row["stage_output_quality_score"]) >= 88 for row in rows) and (critical_value is None or float(critical_value) <= limit)
        return {
            "artifact_type": "phase6_score_snapshot",
            "schema_id": "urn:capcut:remix-reference-video:artifact:phase6-score-snapshot",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "snapshot_id": f"snapshot-{run_id}-{state_revision if state_revision is not None else 0}",
            "run_id": run_id,
            "state_revision": state_revision,
            "lifecycle_status": lifecycle_status,
            "measurement_status": "measured" if quality is not None else "incomplete",
            "approval_status": "provisional",
            "framework_stages": rows,
            "video_quality_score": quality,
            "minimum_video_quality_score": 88,
            "target_video_quality_score": 91,
            "machine_api_critical_path_seconds": critical_value,
            "process_assessment": process_assessment,
            "baseline_comparison": baseline_result,
            "thresholds_not_evaluated": thresholds_not_evaluated,
            "g_b_thresholds_met": bool(thresholds and not (set(thresholds_not_evaluated) - set(baseline_result.get("allowed_not_evaluated_metrics", [])))),
            "owner_g_b_approval_required": True,
            "owner_acknowledgement_required": bool(thresholds_not_evaluated),
            "input_hashes": dict(input_hashes),
            "supersedes_snapshot_id": supersedes_snapshot_id,
        }
