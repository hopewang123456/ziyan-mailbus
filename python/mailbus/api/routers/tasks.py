"""task 路由：创建、派发、推进、取消。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import tasks as mapper
from mailbus.api.schemas.tasks import TaskAdvanceIn, TaskIn, TaskOut, TaskStateFilter
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/tasks", tags=["task"])


def _service(request: Request):
    return request.app.state.container.tasks


@router.get("", response_model=list[TaskOut], summary="任务列表")
def list_tasks(
    request: Request,
    state: TaskStateFilter | None = None,
    owner_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[TaskOut]:
    actor = get_actor(request)
    viewer = None if Capability.ALL in actor.capabilities else actor.employee_id
    views = _service(request).list_tasks(
        state, owner_id, limit=limit, offset=offset, viewer_id=viewer
    )
    return [mapper.to_task_out(view) for view in views]


@router.post("", response_model=TaskOut, status_code=201, summary="创建任务")
@declares(Capability.TASK_CREATE)
def create_task(payload: TaskIn, request: Request) -> TaskOut:
    view = _service(request).create(get_actor(request), mapper.task_command(payload))
    return mapper.to_task_out(view)


@router.get("/{task_id}", response_model=TaskOut, summary="任务详情")
def get_task(task_id: str, request: Request) -> TaskOut:
    actor = get_actor(request)
    viewer = None if Capability.ALL in actor.capabilities else actor.employee_id
    return mapper.to_task_out(_service(request).get(task_id, viewer_id=viewer))


@router.post("/{task_id}/dispatch", response_model=TaskOut, summary="派发任务")
@declares(Capability.TASK_DISPATCH)
def dispatch_task(task_id: str, request: Request) -> TaskOut:
    view = _service(request).dispatch(get_actor(request), task_id)
    return mapper.to_task_out(view)


@router.post("/{task_id}/advance", response_model=TaskOut, summary="推进任务")
@declares(Capability.RESULT_SUBMIT)
def advance_task(
    task_id: str, payload: TaskAdvanceIn, request: Request
) -> TaskOut:
    view = _service(request).advance(
        get_actor(request), task_id, mapper.advance_command(payload)
    )
    return mapper.to_task_out(view)


@router.post("/{task_id}/cancel", response_model=TaskOut, summary="取消任务")
@declares(Capability.TASK_DISPATCH)
def cancel_task(task_id: str, request: Request) -> TaskOut:
    view = _service(request).cancel(get_actor(request), task_id)
    return mapper.to_task_out(view)
