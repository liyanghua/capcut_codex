"""Read-only FastAPI/SSE projection over authoritative task state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .storage import read_json_object, read_jsonl_records


_ARTIFACT_ALLOWLIST = frozenset(
    {
        "remix.mp4",
        "captions.srt",
        "final_validation_report.json",
        "render_report.json",
        "jianying_import_manifest.json",
    }
)
_STAGE_LABELS = {
    "init": "任务准备",
    "split-reference": "参考视频拆解",
    "reference_split": "参考视频拆解",
    "compile-blueprint": "爆款结构与内容蓝图",
    "content_blueprint": "爆款结构与内容蓝图",
    "retrieval": "素材匹配与证据",
    "match-assets": "素材匹配与证据",
    "reconstruction": "配音、剪辑与成片",
    "render-final": "配音、剪辑与成片",
    "final_review": "最终预览审核",
}


class ProgressProjector:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = Path(workspace_root).resolve(strict=True)

    def task_list(self) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for path in sorted(self.workspace_root.iterdir()):
            if not path.is_dir() or path.is_symlink() or not (path / "pipeline_state.json").is_file():
                continue
            result.append(self.task_detail(path.name)["progress"])
        return result

    def task_detail(self, task_id: str) -> dict[str, object]:
        root = self._task(task_id)
        state = read_json_object(root / "pipeline_state.json")
        revision = state.get("state_revision")
        active = state.get("active_stage") or state.get("current_stage")
        gates = state.get("gate_status") if isinstance(state.get("gate_status"), dict) else {}
        blockers = state.get("blockers") if isinstance(state.get("blockers"), list) else []
        progress = {
            "task_id": task_id,
            "run_id": state.get("run_id"),
            "status": self._status(gates, blockers),
            "current_stage": _STAGE_LABELS.get(str(active), str(active or "任务准备")),
            "state_revision": revision,
            "gate_status": gates,
            "blocker_count": len(blockers),
        }
        return {
            "etag": f'"revision-{revision}"',
            "progress": progress,
            "artifacts": sorted(
                name
                for name in state.get("artifacts", {})
                if name in _ARTIFACT_ALLOWLIST
            ),
        }

    def artifact_metadata(self, task_id: str, name: str) -> dict[str, object]:
        if name not in _ARTIFACT_ALLOWLIST:
            raise KeyError(name)
        root = self._task(task_id)
        state = read_json_object(root / "pipeline_state.json")
        record = state.get("artifacts", {}).get(name)
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise KeyError(name)
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise KeyError(name)
        path = (root / relative).resolve(strict=True)
        if root not in path.parents or not path.is_file():
            raise KeyError(name)
        return {
            "name": name,
            "sha256": record.get("sha256"),
            "size_bytes": path.stat().st_size,
        }

    def revision_notices(
        self, task_id: str, *, last_event_id: str | None = None
    ) -> list[dict[str, str]]:
        root = self._task(task_id)
        try:
            after = int(last_event_id or 0)
        except ValueError:
            after = 0
        notices: list[dict[str, str]] = []
        seen: set[int] = set()
        for record in read_jsonl_records(root / "pipeline_events.jsonl"):
            sequence = record.get("sequence")
            if not isinstance(sequence, int) or sequence <= after or sequence in seen:
                continue
            seen.add(sequence)
            payload = {
                "state_revision": record.get("state_revision"),
                "event_type": record.get("event_type"),
            }
            notices.append(
                {
                    "id": str(sequence),
                    "event": "revision",
                    "data": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                }
            )
        return notices

    def _task(self, task_id: str) -> Path:
        if not isinstance(task_id, str) or not task_id or Path(task_id).name != task_id:
            raise KeyError(task_id)
        root = (self.workspace_root / task_id).resolve(strict=True)
        if self.workspace_root not in root.parents or root.is_symlink() or not root.is_dir():
            raise KeyError(task_id)
        return root

    @staticmethod
    def _status(gates: dict[str, object], blockers: list[object]) -> str:
        if blockers or "blocked" in gates.values():
            return "blocked"
        if "awaiting_user" in gates.values():
            return "awaiting_user"
        if gates.get("gate5") == "approved":
            return "completed"
        return "running"


def create_app(workspace_root: Path) -> Any:
    try:
        from fastapi import FastAPI, Header, HTTPException, Response
        from fastapi.responses import StreamingResponse
    except ImportError as error:
        raise RuntimeError(
            "FastAPI optional extra is required: install remix-reference-video[api]"
        ) from error

    projector = ProgressProjector(workspace_root)
    app = FastAPI(title="Remix Production Progress", version="0.1.0")

    @app.get("/tasks")
    def tasks() -> list[dict[str, object]]:
        return projector.task_list()

    @app.get("/tasks/{task_id}")
    def task(task_id: str, response: Response) -> dict[str, object]:
        try:
            detail = projector.task_detail(task_id)
        except (KeyError, OSError):
            raise HTTPException(status_code=404, detail="task not found") from None
        response.headers["ETag"] = str(detail["etag"])
        return detail

    @app.get("/tasks/{task_id}/artifacts/{name}")
    def artifact(task_id: str, name: str) -> dict[str, object]:
        try:
            return projector.artifact_metadata(task_id, name)
        except (KeyError, OSError):
            raise HTTPException(status_code=404, detail="artifact not found") from None

    @app.get("/tasks/{task_id}/events")
    def events(
        task_id: str,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> Any:
        try:
            notices = projector.revision_notices(task_id, last_event_id=last_event_id)
        except (KeyError, OSError):
            raise HTTPException(status_code=404, detail="task not found") from None

        def stream() -> Any:
            for notice in notices:
                yield (
                    f"id: {notice['id']}\n"
                    f"event: {notice['event']}\n"
                    f"data: {notice['data']}\n\n"
                )

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app
