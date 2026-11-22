"""workflow 路由：定义与不可变版本。"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import workflow as mapper
from mailbus.api.schemas.workflow import VersionIn, VersionOut, WorkflowIn, WorkflowOut
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/workflows", tags=["workflow"])


def _service(request: Request):
    return request.app.state.container.workflows


@router.get("", response_model=list[WorkflowOut], summary="流程列表")
def list_workflows(request: Request) -> list[WorkflowOut]:
    get_actor(request)
    return [mapper.to_workflow_out(view) for view in _service(request).list_definitions()]


@router.post("", response_model=WorkflowOut, status_code=201, summary="创建流程定义")
@declares(Capability.WORKFLOW_CREATE)
def create_workflow(payload: WorkflowIn, request: Request) -> WorkflowOut:
    view = _service(request).create_definition(
        get_actor(request), mapper.workflow_command(payload)
    )
    return mapper.to_workflow_out(view)


@router.get("/{workflow_id}", response_model=WorkflowOut, summary="流程定义详情")
def get_workflow(workflow_id: str, request: Request) -> WorkflowOut:
    get_actor(request)
    return mapper.to_workflow_out(_service(request).get_definition(workflow_id))


@router.patch("/{workflow_id}", response_model=WorkflowOut, summary="重命名流程")
@declares(Capability.WORKFLOW_MODIFY)
def rename_workflow(
    workflow_id: str, payload: WorkflowIn, request: Request
) -> WorkflowOut:
    view = _service(request).rename_definition(
        get_actor(request), workflow_id, mapper.workflow_command(payload)
    )
    return mapper.to_workflow_out(view)


@router.delete("/{workflow_id}", status_code=204, summary="删除流程定义")
@declares(Capability.WORKFLOW_MODIFY)
def delete_workflow(workflow_id: str, request: Request) -> Response:
    _service(request).delete_definition(get_actor(request), workflow_id)
    return Response(status_code=204)


@router.get(
    "/{workflow_id}/versions", response_model=list[VersionOut], summary="版本列表"
)
def list_versions(workflow_id: str, request: Request) -> list[VersionOut]:
    get_actor(request)
    return [
        mapper.to_version_out(view)
        for view in _service(request).list_versions(workflow_id)
    ]


@router.post(
    "/{workflow_id}/versions",
    response_model=VersionOut,
    status_code=201,
    summary="新增草稿版本",
)
@declares(Capability.WORKFLOW_MODIFY)
def add_version(
    workflow_id: str, payload: VersionIn, request: Request
) -> VersionOut:
    view = _service(request).add_version(
        get_actor(request), workflow_id, mapper.version_command(payload)
    )
    return mapper.to_version_out(view)


@router.post(
    "/{workflow_id}/versions/{version}/publish",
    response_model=VersionOut,
    summary="发布版本",
)
@declares(Capability.WORKFLOW_MODIFY)
def publish_version(
    workflow_id: str, version: int, request: Request
) -> VersionOut:
    view = _service(request).publish_version(get_actor(request), workflow_id, version)
    return mapper.to_version_out(view)
