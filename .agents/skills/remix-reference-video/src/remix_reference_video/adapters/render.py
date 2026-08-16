"""Validated final rendering, Gate 5 packaging, and guarded archival."""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from ..artifact_validator import ArtifactValidator
from ..storage import TaskStorage, atomic_write_json, read_json_object
from ..transactions import ArtifactPromotion, TransactionManager


class RenderError(RuntimeError):
    pass


class RenderAdapter:
    def __init__(
        self,
        storage: TaskStorage,
        *,
        renderer: Callable[..., Mapping[str, object]],
        media_probe: Callable[[Path], Mapping[str, object]],
    ) -> None:
        self.storage = storage
        self.root = storage.task_root
        self.renderer = renderer
        self.media_probe = media_probe

    def render_final(
        self,
        *,
        manage_state: bool = True,
        state_override: Mapping[str, object] | None = None,
    ) -> dict[str, dict[str, str]]:
        state = self.storage.read_state() if state_override is None else dict(state_override)
        self._verify_prerequisites(state)
        timeline_path = self.root / "reconstruction_timeline.json"
        material_path = self.root / "material_manifest.json"
        captions_path = self.root / "captions.srt"
        timeline = read_json_object(timeline_path)
        read_json_object(material_path)
        if not captions_path.is_file() or captions_path.is_symlink():
            raise RenderError("captions.srt is required")
        revision = int(state["state_revision"])
        transaction_id = f"render-final-r{revision}"
        staging = self.root / ".staging" / transaction_id
        staging.mkdir(parents=True, exist_ok=True)
        video = staging / "remix.mp4"
        render_details = self.renderer(
            output_path=video,
            timeline=timeline,
            material_manifest=material_path,
            captions_path=captions_path,
            profile={"width": 1080, "height": 1920, "fps": 60},
        )
        if not video.is_file() or video.is_symlink():
            raise RenderError("renderer did not produce remix.mp4")
        media = dict(self.media_probe(video))
        self._validate_media(media, float(timeline.get("duration_seconds", -1)))
        staged_captions = staging / "captions.srt"
        shutil.copy2(captions_path, staged_captions)
        envelope = {
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
        }
        atomic_write_json(
            staging / "render_report.json",
            {
                **envelope,
                "artifact_type": "render_report",
                "schema_id": "urn:capcut:remix-reference-video:artifact:render-report",
                "status": "passed",
                "media": media,
                "renderer": dict(render_details),
                "inputs": {
                    timeline_path.name: self._sha256(timeline_path),
                    material_path.name: self._sha256(material_path),
                    captions_path.name: self._sha256(captions_path),
                },
            },
        )
        atomic_write_json(
            staging / "final_validation_report.json",
            {
                **envelope,
                "artifact_type": "final_validation_report",
                "schema_id": "urn:capcut:remix-reference-video:artifact:final-validation-report",
                "status": "passed",
                "hard_gate_checks": {
                    "streams": "passed",
                    "duration": "passed",
                    "timeline": "passed",
                    "captions_sidecar": "passed",
                },
            },
        )
        atomic_write_json(
            staging / "jianying_import_manifest.json",
            {
                **envelope,
                "artifact_type": "jianying_import_manifest",
                "schema_id": "urn:capcut:remix-reference-video:artifact:jianying-import-manifest",
                "editable_draft_generated": False,
                "canvas": {"width": 1080, "height": 1920, "fps": 60},
                "duration_seconds": timeline.get("duration_seconds"),
                "timeline": timeline.get("fragments", []),
                "captions_path": "captions.srt",
            },
        )
        names = (
            "remix.mp4",
            "captions.srt",
            "final_validation_report.json",
            "render_report.json",
            "jianying_import_manifest.json",
        )
        artifacts = {
            name: {
                "path": name,
                "sha256": self._sha256(
                    captions_path if name == "captions.srt" else staging / name
                ),
            }
            for name in names
        }
        if not manage_state:
            for name in names:
                if name == "captions.srt":
                    continue
                shutil.copy2(staging / name, self.root / name)
            return artifacts
        gates = dict(state["gate_status"])
        gates["gate5"] = "awaiting_user"
        stages = dict(state.get("stages", {}))
        stages["render"] = {"status": "awaiting_user"}
        stages["final_review"] = {"status": "awaiting_user"}
        promotions = tuple(
            ArtifactPromotion(
                staged_path=staging / name,
                final_path=self.root / name,
                expected_type=(
                    name.removesuffix(".json") if name.endswith(".json") else None
                ),
            )
            for name in names
            if name != "captions.srt"
        )
        manager = TransactionManager(self.storage)
        manager.prepare(
            transaction_id=transaction_id,
            expected_revision=revision,
            state_changes={
                "active_stage": "final_review",
                "gate_status": gates,
                "stages": stages,
                "artifacts": {**dict(state.get("artifacts", {})), **artifacts},
            },
            event={"event_type": "render.final.completed"},
            metric=None,
            promotions=promotions,
        )
        try:
            manager.commit(transaction_id)
        except Exception:
            manager.reconcile(transaction_id)
            raise
        return artifacts

    def build_gate5_package(
        self,
        *,
        created_at: str,
        state_override: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        state = self.storage.read_state() if state_override is None else dict(state_override)
        if state.get("gate_status", {}).get("gate5") != "awaiting_user":
            raise RenderError("Gate 5 is not awaiting user")
        artifacts = state.get("artifacts", {})
        result = ArtifactValidator(self.root).validate_gate5_bundle(artifacts)
        if not result.valid:
            raise RenderError("; ".join(result.errors))
        return {
            "artifact_type": "gate_review_package",
            "schema_id": "urn:capcut:remix-reference-video:artifact:gate-review-package",
            "schema_version": "1.0.0",
            "contract_version": "2.0.0-alpha.1",
            "skill_version": "2.0.0-alpha.1",
            "run_id": state["run_id"],
            "gate_id": "gate5",
            "state_revision": state["state_revision"],
            "created_at": created_at,
            "input_hashes": {
                str(record["path"]): str(record["sha256"])
                for name, record in artifacts.items()
                if name in {
                    "remix.mp4",
                    "captions.srt",
                    "final_validation_report.json",
                    "render_report.json",
                    "jianying_import_manifest.json",
                }
                and isinstance(record, Mapping)
            },
        }

    def archive_approved(
        self,
        *,
        final_root: Path,
        output_name: str,
        state_override: Mapping[str, object] | None = None,
    ) -> Path:
        state = self.storage.read_state() if state_override is None else dict(state_override)
        if state.get("execution_mode") == "manual-contract-only":
            raise RenderError("manual-contract-only pilot must not be archived")
        if state.get("gate_status", {}).get("gate5") != "approved":
            raise RenderError("Gate 5 approval is required for archive")
        source = (self.root / "remix.mp4").resolve(strict=True)
        destination = Path(final_root).resolve(strict=False) / output_name
        if destination.exists():
            raise RenderError("archive destination already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination

    @staticmethod
    def _verify_prerequisites(state: Mapping[str, object]) -> None:
        gates = state.get("gate_status")
        stages = state.get("stages")
        required = (
            "gate1",
            "gate2",
            "gate3_material_selection",
            "gate3_evidence_closure",
            "gate3",
            "gate4_pre_generation",
            "gate4_post_generation",
            "gate4",
        )
        if not isinstance(gates, Mapping) or any(gates.get(gate) != "approved" for gate in required):
            raise RenderError("Gate prerequisites are not approved")
        if not isinstance(stages, Mapping) or any(
            not isinstance(stages.get(stage), Mapping)
            or stages[stage].get("status") != "approved"
            for stage in ("reference_split", "content_blueprint")
        ):
            raise RenderError("business stage prerequisites are not approved")

    @staticmethod
    def _validate_media(media: Mapping[str, object], duration: float) -> None:
        if media.get("width") != 1080 or media.get("height") != 1920:
            raise RenderError("final media must be 1080x1920")
        if media.get("fps") != 60:
            raise RenderError("final media must be 60fps")
        if (
            media.get("video_codec") != "h264"
            or media.get("pixel_format") != "yuv420p"
            or media.get("video_stream_count") != 1
            or media.get("audio_stream_count") != 1
            or media.get("audio_codec") != "aac"
            or media.get("audio_sample_rate") != 44100
            or media.get("audio_channels") != 2
        ):
            raise RenderError("final media stream profile is invalid")
        actual = media.get("duration_seconds")
        if not isinstance(actual, (int, float)) or abs(float(actual) - duration) > 1 / 60 + 1e-9:
            raise RenderError("final media duration differs from timeline")

    @staticmethod
    def _sha256(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
