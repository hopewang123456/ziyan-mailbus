"""任务域路由：冻结契约实现 + 旧派发/推进别名（deprecated）。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse

from mailbus.api.deps import SELF, declares, get_actor
from mailbus.api.mappers import task_domain as mapper
from mailbus.api.schemas.contract.task import (
    ArtifactOut,
    CancelIn,
    RerunJoinIn,
    ResultIn,
    TaskCountersOut,
    TaskCreateIn,
    TaskDetailOut,
    TaskListOut,
    TaskTraceOut,
)
from mailbus.application.task.dto import (
    CreateTaskCommand,
    RerunJoinCommand,
    SubmitResultCommand,
)
from mailbus.core.shared.errors import ResourceGoneError, UnprocessableError
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/tasks", tags=["task"])
artifact_router = APIRouter(prefix="/api", tags=["task"])

_MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def _engine(request: Request):
    return request.app.state.container.task_engine


@router.get("", response_model=TaskListOut, summary="任务列表")
def list_tasks(
    request: Request,
    state: str | None = None,
    owner_id: str | None = None,
    workflow_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> TaskListOut:
    views, total = _engine(request).list_tasks(
        get_actor(request), state, owner_id, workflow_id, limit, offset)
    return mapper.to_list(views, total, limit, offset)


@router.post("", response_model=TaskDetailOut, status_code=201, summary="创建并启动任务")
@declares(Capability.TASK_CREATE)
def create_task(payload: TaskCreateIn, request: Request) -> TaskDetailOut:
    view = _engine(request).create(get_actor(request), CreateTaskCommand(
        title=payload.title,
        workflow_id=payload.workflow_id,
        owner_id=payload.owner_id,
        variables=dict(payload.variables),
    ))
    return mapper.to_detail(view)


@router.get("/summary", response_model=TaskCountersOut, summary="导航角标")
def task_summary(request: Request) -> TaskCountersOut:
    return mapper.to_counters(_engine(request).counters(get_actor(request)))


@router.get("/{task_id}", response_model=TaskDetailOut, summary="任务详情")
def get_task(task_id: str, request: Request) -> TaskDetailOut:
    return mapper.to_detail(_engine(request).get(get_actor(request), task_id))


@router.get("/{task_id}/trace", response_model=TaskTraceOut, summary="任务追迹")
def get_task_trace(task_id: str, request: Request) -> TaskTraceOut:
    return mapper.to_trace(_engine(request).get(get_actor(request), task_id))


@router.post(
    "/{task_id}/nodes/{node_id}/claim",
    response_model=TaskDetailOut,
    summary="CAS 认领节点",
)
@declares(SELF)
def claim_node(task_id: str, node_id: str, request: Request) -> TaskDetailOut:
    view = _engine(request).claim(get_actor(request), task_id, node_id)
    return mapper.to_detail(view)


@router.post(
    "/{task_id}/nodes/{node_id}/result",
    response_model=TaskDetailOut,
    summary="提交节点结果",
)
@declares(Capability.RESULT_SUBMIT)
def submit_result(
    task_id: str, node_id: str, payload: ResultIn, request: Request
) -> TaskDetailOut:
    view = _engine(request).submit(get_actor(request), task_id, node_id,
                                   SubmitResultCommand(
                                       attempt_no=payload.attempt_no,
                                       result=payload.result,
                                       artifact_ids=tuple(payload.artifact_ids),
                                   ))
    return mapper.to_detail(view)


@router.post(
    "/{task_id}/nodes/{node_id}/artifacts",
    response_model=ArtifactOut,
    summary="上传任务节点产物",
)
@declares(Capability.RESULT_SUBMIT)
async def upload_artifact(
    task_id: str,
    node_id: str,
    request: Request,
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
) -> ArtifactOut:
    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        raise UnprocessableError("产物文件超过 100MB 上限")
    view = _engine(request).upload_artifact(
        get_actor(request), task_id, node_id,
        file.filename or "artifact", data, description,
    )
    return mapper.to_artifact(view)


@router.post("/{task_id}/cancel", response_model=TaskDetailOut, summary="取消任务")
@declares(SELF)
def cancel_task(
    task_id: str, request: Request, payload: CancelIn | None = None
) -> TaskDetailOut:
    reason = payload.reason if payload is not None else "manual"
    return mapper.to_detail(_engine(request).cancel(get_actor(request), task_id, reason))


@router.post(
    "/{task_id}/nodes/{node_id}/rerun-join",
    response_model=TaskDetailOut,
    summary="显式重跑汇聚",
)
@declares(SELF)
def rerun_join(
    task_id: str, node_id: str, payload: RerunJoinIn, request: Request
) -> TaskDetailOut:
    view = _engine(request).rerun_join(
        get_actor(request), task_id, node_id,
        RerunJoinCommand(fanout_group=payload.fanout_group, scope=payload.scope))
    return mapper.to_detail(view)


@artifact_router.get(
    "/artifacts/{artifact_id}/download",
    summary="产物签名下载",
    response_class=FileResponse,
)
@declares(Capability.ARTIFACT_READ_ALL)
def download_artifact(artifact_id: str, request: Request):
    artifact = _engine(request).download(get_actor(request), artifact_id)
    path = Path(artifact.file_path)
    if not path.is_file():
        raise ResourceGoneError("产物文件已失效")
    return FileResponse(path, filename=artifact.file_name)
