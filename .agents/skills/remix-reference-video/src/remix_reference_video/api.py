"""Local progress and actor-bound review workbench API."""

from __future__ import annotations

import json
import hashlib
import html
import mimetypes
import os
from pathlib import Path
from typing import Any, Mapping

try:  # FastAPI remains an optional runtime extra.
    from fastapi import BackgroundTasks as FastAPIBackgroundTasks
    from fastapi import Request as FastAPIRequest
    from fastapi import Response as FastAPIResponse
except ImportError:  # pragma: no cover - exercised by non-API installations
    FastAPIBackgroundTasks = Any  # type: ignore[misc,assignment]
    FastAPIRequest = Any  # type: ignore[misc,assignment]
    FastAPIResponse = Any  # type: ignore[misc,assignment]

from .change_service import ChangeConflict, ChangeImpactAnalyzer, ChangeService, WorkbenchOrchestrator
from .contracts import CANONICAL_GATE_ORDER
from .review_session import ReviewSessionError, ReviewSessionService
from .review_view import ReviewViewBuilder, ReviewViewError
from .run_registry import RunRegistry, RunRegistryError
from .storage import StorageError, read_json_object, read_jsonl_records
from .workbench_decision import WorkbenchConflict, WorkbenchDecisionService
from .workspace_media import WorkspaceMediaAuthorizer, WorkspaceMediaError
from .workspace_view import WorkbenchWorkspaceBuilder, WorkspaceViewError


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


def create_app(
    workspace_root: Path,
    *,
    actor: str = "local-operator",
    role: str = "operator",
    runner_factory: object | None = None,
    auto_resume_changes: bool = True,
) -> Any:
    try:
        from fastapi import BackgroundTasks, Body, FastAPI, Header, HTTPException, Request, Response
        from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
    except ImportError as error:
        raise RuntimeError(
            "FastAPI optional extra is required: install remix-reference-video[api]"
        ) from error

    workspace = Path(workspace_root).resolve(strict=True)
    projector = ProgressProjector(workspace)
    registry = RunRegistry(workspace)
    ui_mode = os.environ.get("WORKBENCH_UI_MODE", "legacy").strip().lower()
    if ui_mode not in {"legacy", "workspace"}:
        ui_mode = "legacy"
    app = FastAPI(title="Remix Review Workbench", version="0.2.0")

    def run_task(run_id: str) -> Path:
        try:
            return registry.resolve(run_id)
        except RunRegistryError as error:
            status = 404 if "not registered" in str(error) else 409
            raise HTTPException(status_code=status, detail={"error_code":"run_registry_error","message":str(error)}) from None

    def current_gate(task_root: Path) -> str:
        state = read_json_object(task_root / "pipeline_state.json")
        gates = state.get("gate_status")
        if not isinstance(gates, Mapping):
            raise HTTPException(status_code=409, detail={"error_code":"invalid_state","message":"gate_status is invalid"})
        for gate_id in CANONICAL_GATE_ORDER:
            if gates.get(gate_id) in {"awaiting_user", "stale", "blocked", "rejected"}:
                return gate_id
        revision = state.get("state_revision")
        for gate_id in reversed(CANONICAL_GATE_ORDER):
            package = task_root / "gate_review_packages" / f"{gate_id}.json"
            if package.is_file() and not package.is_symlink() and read_json_object(package).get("state_revision") == revision:
                return gate_id
        raise HTTPException(status_code=409, detail={"error_code":"review_not_ready","message":"no current Gate review package"})

    def sse(notices: list[dict[str, str]]) -> Any:
        def stream() -> Any:
            yield "retry: 15000\n\n"
            for notice in notices:
                yield f"id: {notice['id']}\nevent: {notice['event']}\ndata: {notice['data']}\n\n"
        return StreamingResponse(stream(), media_type="text/event-stream")

    def conflict(error: Exception, *, gate_id: str | None = None) -> Any:
        if isinstance(error, WorkbenchConflict):
            return JSONResponse(status_code=409, content={"error_code":"review_conflict","message":str(error),"current_revision":error.current_revision,"refresh_path":error.refresh_path})
        return JSONResponse(status_code=409, content={"error_code":"change_conflict","message":str(error),"refresh_path":f"/api/v1/runs/current/review" if gate_id is None else f"/api/v1/runs/current/gates/{gate_id}/review"})

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

        return sse(notices)

    @app.get("/api/v1/runs/{run_id}/review")
    def run_review(run_id: str, response: FastAPIResponse) -> dict[str, object]:
        task_root = run_task(run_id)
        gate_id = current_gate(task_root)
        try:
            view = ReviewViewBuilder(task_root).build(gate_id)
        except (ReviewViewError, OSError) as error:
            raise HTTPException(status_code=409, detail={"error_code":"review_conflict","message":str(error)}) from None
        response.headers["ETag"] = f'"review-{view["bound_package_sha256"]}"'
        return view

    @app.get("/api/v1/runs/{run_id}/workspace")
    def run_workspace(run_id: str, request: FastAPIRequest, response: FastAPIResponse) -> Any:
        task_root = run_task(run_id)
        gate_id = current_gate(task_root)
        try:
            view = WorkbenchWorkspaceBuilder(task_root).build(gate_id)
        except (WorkspaceViewError, OSError) as error:
            raise HTTPException(status_code=409, detail={"error_code": "workspace_conflict", "message": str(error)}) from None
        snapshot = json.dumps(view, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        etag = '"workspace-' + hashlib.sha256(snapshot).hexdigest() + '"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        response.headers["ETag"] = etag
        return view

    @app.post("/api/v1/runs/{run_id}/review-session")
    def open_review_session(run_id: str, payload: dict[str, object] = Body(...)) -> dict[str, object]:
        task_root = run_task(run_id)
        gate_id = payload.get("gate_id")
        if not isinstance(gate_id, str):
            raise HTTPException(status_code=422, detail="gate_id is required")
        if gate_id != current_gate(task_root):
            raise HTTPException(status_code=409, detail={"error_code":"review_conflict","message":"Gate is not current"})
        try:
            return ReviewSessionService(task_root, actor=actor, role=role).open(gate_id)
        except ReviewSessionError as error:
            raise HTTPException(status_code=409, detail={"error_code":"review_conflict","message":str(error)}) from None

    @app.post("/api/v1/runs/{run_id}/review-session/events")
    def review_event(run_id: str, payload: dict[str, object] = Body(...)) -> dict[str, object]:
        task_root = run_task(run_id)
        session_id = payload.get("session_id")
        event_type = payload.get("event_type")
        event_payload = payload.get("payload", {})
        if not isinstance(session_id, str) or not isinstance(event_type, str) or not isinstance(event_payload, Mapping):
            raise HTTPException(status_code=422, detail="session_id, event_type and payload are required")
        try:
            return ReviewSessionService(task_root, actor=actor, role=role).record_intent(session_id, event_type, event_payload)
        except ReviewSessionError as error:
            return conflict(error)

    @app.post("/api/v1/runs/{run_id}/gates/{gate_id}/decisions")
    def decide(run_id: str, gate_id: str, payload: dict[str, object] = Body(...)) -> Any:
        task_root = run_task(run_id)
        session_id = payload.get("session_id")
        if not isinstance(session_id, str):
            raise HTTPException(status_code=422, detail="session_id is required")
        decision_payload = {key:value for key,value in payload.items() if key != "session_id" and key != "actor"}
        try:
            return WorkbenchDecisionService(task_root, actor=actor, role=role).submit(session_id=session_id, gate_id=gate_id, payload=decision_payload)
        except WorkbenchConflict as error:
            return conflict(error, gate_id=gate_id)

    @app.post("/api/v1/runs/{run_id}/gates/{gate_id}/changes/preview")
    def preview_change(run_id: str, gate_id: str, payload: dict[str, object] = Body(...)) -> Any:
        task_root = run_task(run_id)
        session_id = payload.get("session_id")
        request_value = payload.get("request")
        if not isinstance(session_id, str) or not isinstance(request_value, Mapping):
            raise HTTPException(status_code=422, detail="session_id and request are required")
        try:
            return ChangeImpactAnalyzer(task_root, actor=actor, role=role).preview(session_id=session_id, gate_id=gate_id, request=request_value)
        except ChangeConflict as error:
            return conflict(error, gate_id=gate_id)

    @app.post("/api/v1/runs/{run_id}/gates/{gate_id}/changes")
    def apply_change(run_id: str, gate_id: str, background_tasks: FastAPIBackgroundTasks, payload: dict[str, object] = Body(...)) -> Any:
        task_root = run_task(run_id)
        session_id = payload.get("session_id")
        request_value = payload.get("request")
        preview_hash = payload.get("preview_hash")
        idempotency_key = payload.get("idempotency_key")
        if not all(isinstance(item, str) for item in (session_id, preview_hash, idempotency_key)) or not isinstance(request_value, Mapping):
            raise HTTPException(status_code=422, detail="change binding is incomplete")
        try:
            result = ChangeService(task_root, actor=actor, role=role).apply(session_id=session_id, gate_id=gate_id, request=request_value, preview_hash=preview_hash, idempotency_key=idempotency_key)
        except ChangeConflict as error:
            return conflict(error, gate_id=gate_id)
        if auto_resume_changes:
            def resume_quietly() -> None:
                try:
                    WorkbenchOrchestrator(workspace, actor=actor, runner_factory=runner_factory).resume_job(run_id=run_id, job_id=str(result["job_id"]))
                except BaseException:
                    return
            background_tasks.add_task(resume_quietly)
        return result

    @app.post("/api/v1/runs/{run_id}/jobs/{job_id}/resume")
    def resume_job(run_id: str, job_id: str) -> Any:
        try:
            return WorkbenchOrchestrator(workspace, actor=actor, runner_factory=runner_factory).resume_job(run_id=run_id, job_id=job_id)
        except (ChangeConflict, StorageError) as error:
            return conflict(error)

    @app.get("/api/v1/runs/{run_id}/events")
    def run_events(run_id: str, last_event_id: str | None = Header(default=None, alias="Last-Event-ID")) -> Any:
        task_root = run_task(run_id)
        try:
            after = int(last_event_id or 0)
        except ValueError:
            after = 0
        notices = []
        for record in read_jsonl_records(task_root / "pipeline_events.jsonl"):
            sequence = record.get("sequence")
            if not isinstance(sequence, int) or sequence <= after:
                continue
            notices.append({"id":str(sequence),"event":"revision","data":json.dumps({"state_revision":record.get("state_revision"),"event_type":record.get("event_type")},ensure_ascii=False,separators=(",",":"))})
        return sse(notices)

    @app.get("/api/v1/runs/{run_id}/media/{relative_path:path}")
    def media(run_id: str, relative_path: str, request: FastAPIRequest) -> Any:
        task_root = run_task(run_id)
        gate_id = current_gate(task_root)
        try:
            workspace_view = WorkbenchWorkspaceBuilder(task_root).build(gate_id)
            authorizer = WorkspaceMediaAuthorizer(task_root)
            try:
                authorized = authorizer.authorize(
                    workspace_view,
                    relative_path,
                    run_id=run_id,
                    state_revision=workspace_view["state_revision"],
                    package_revision=workspace_view.get("package_revision"),
                )
            except WorkspaceMediaError:
                legacy_view = ReviewViewBuilder(task_root).build(gate_id)
                legacy_paths = [
                    item.get("path") for item in legacy_view.get("evidence", [])
                    if isinstance(item, Mapping) and item.get("status") == "available" and isinstance(item.get("path"), str)
                ]
                legacy_projection = dict(workspace_view)
                legacy_projection["media_allowlist"] = sorted(set(workspace_view.get("media_allowlist", [])) | set(legacy_paths))
                authorized = authorizer.authorize(legacy_projection, relative_path, run_id=run_id, state_revision=workspace_view["state_revision"], package_revision=workspace_view.get("package_revision"))
        except (WorkspaceViewError, ReviewViewError, WorkspaceMediaError, OSError) as error:
            raise HTTPException(status_code=404, detail="media not found") from error
        resolved = task_root / authorized
        data = resolved.read_bytes()
        etag = '"sha256-' + hashlib.sha256(data).hexdigest() + '"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag":etag})
        media_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        headers = {"Accept-Ranges":"bytes","ETag":etag}
        range_header = request.headers.get("range")
        if not range_header:
            return Response(content=data, media_type=media_type, headers={**headers,"Content-Length":str(len(data))})
        parsed = _parse_byte_range(range_header, len(data))
        if parsed is None:
            return Response(status_code=416, headers={**headers,"Content-Range":f"bytes */{len(data)}"})
        start, end = parsed
        chunk = data[start:end + 1]
        return Response(status_code=206, content=chunk, media_type=media_type, headers={**headers,"Content-Range":f"bytes {start}-{end}/{len(data)}","Content-Length":str(len(chunk))})

    static_root = Path(__file__).resolve().parent

    @app.get("/workbench/runs/{run_id}", response_class=HTMLResponse)
    def workbench_page(run_id: str) -> str:
        run_task(run_id)
        template_name = "review_workbench.html" if ui_mode == "workspace" else "review_workbench_legacy.html"
        template = (static_root / "templates" / template_name).read_text(encoding="utf-8")
        return template.replace("__RUN_ID__", html.escape(run_id, quote=True))

    @app.get("/static/review_workbench.js")
    def workbench_js() -> Response:
        name = "review_workbench.js" if ui_mode == "workspace" else "review_workbench_legacy.js"
        return Response(content=(static_root / "static" / name).read_text(encoding="utf-8"), media_type="text/javascript")

    @app.get("/static/review_workbench.css")
    def workbench_css() -> Response:
        name = "review_workbench.css" if ui_mode == "workspace" else "review_workbench_legacy.css"
        return Response(content=(static_root / "static" / name).read_text(encoding="utf-8"), media_type="text/css")

    return app


def _parse_byte_range(value: str, size: int) -> tuple[int, int] | None:
    if size <= 0 or not value.startswith("bytes=") or "," in value:
        return None
    raw = value[6:]
    if "-" not in raw:
        return None
    first, last = raw.split("-", 1)
    try:
        if not first:
            length = int(last)
            if length <= 0:
                return None
            return max(0, size - length), size - 1
        start = int(first)
        end = size - 1 if not last else int(last)
    except ValueError:
        return None
    if start < 0 or start >= size or end < start:
        return None
    return start, min(end, size - 1)


def serve_workbench(
    workspace_root: Path,
    *,
    actor: str,
    role: str = "operator",
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("workbench host must be loopback")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("workbench port is invalid")
    try:
        import uvicorn
    except ImportError as error:
        raise RuntimeError("FastAPI/Uvicorn optional extra is required") from error
    uvicorn.run(create_app(workspace_root, actor=actor, role=role), host=host, port=port)
