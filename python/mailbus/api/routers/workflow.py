"""工作流域路由：冻结契约（WF-01..WF-08）+ 旧别名（deprecated，不进契约）。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from mailbus.api.deps import SELF, declares, get_actor
from mailbus.api.mappers import workflow as mapper
from mailbus.api.schemas.contract.workflow import (
    GraphIn,
    GraphOut,
    ValidateOut,
    VersionListOut,
    VersionOut,
    WorkflowIn,
    WorkflowListOut,
    WorkflowOut,
)
from mailbus.api.schemas.workflow import VersionIn
from mailbus.api.schemas.workflow import VersionOut as LegacyVersionOut
from mailbus.api.schemas.workflow import WorkflowIn as LegacyWorkflowIn
from mailbus.api.schemas.workflow import WorkflowOut as LegacyWorkflowOut
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/workflows", tags=["workflow"])


def _service(request: Request):
    return request.app.state.container.workflows


@router.get("", response_model=WorkflowListOut, summary="流程列表")
def list_workflows(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> WorkflowListOut:
    views, total = _service(request).list_definitions(limit, offset)
    return WorkflowListOut(
        items=[mapper.to_contract_workflow_out(item) for item in views],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=WorkflowOut, status_code=201, summary="创建流程定义")
@declares(Capability.WORKFLOW_CREATE)
def create_workflow(payload: WorkflowIn, request: Request) -> WorkflowOut:
    graph = payload.graph
    view = _service(request).create_definition(
        get_actor(request),
        mapper.workflow_command(payload),
        None if graph is None else mapper.graph_nodes(graph),
        None if graph is None else mapper.graph_edges(graph),
    )
    return mapper.to_contract_workflow_out(view)


@router.get("/{workflow_id}", response_model=WorkflowOut, summary="流程定义详情")
def get_workflow(workflow_id: str, request: Request) -> WorkflowOut:
    return mapper.to_contract_workflow_out(
        _service(request).get_definition(workflow_id)
    )


@router.delete("/{workflow_id}", status_code=204, summary="删除流程定义")
@declares(Capability.WORKFLOW_MODIFY)
def delete_workflow(workflow_id: str, request: Request) -> None:
    _service(request).delete_definition(get_actor(request), workflow_id)


@router.get(
    "/{workflow_id}/versions", response_model=VersionListOut, summary="版本列表"
)
def list_versions(
    workflow_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> VersionListOut:
    views, total = _service(request).list_versions(workflow_id, limit, offset)
    return VersionListOut(
        items=[mapper.to_contract_version_out(item) for item in views],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{workflow_id}/versions/{version}/graph",
    response_model=GraphOut,
    summary="读取 Graph",
)
def get_graph(workflow_id: str, version: int, request: Request) -> GraphOut:
    return mapper.to_graph_out(_service(request).get_graph(workflow_id, version))


@router.put(
    "/{workflow_id}/versions/{version}/graph",
    response_model=GraphOut,
    summary="保存 Graph",
)
@declares(Capability.WORKFLOW_MODIFY)
def put_graph(
    workflow_id: str,
    version: int,
    payload: GraphIn,
    request: Request,
    force: bool = False,
) -> GraphOut:
    nodes, edges = mapper.graph_in(payload)
    view = _service(request).save_graph(
        get_actor(request),
        workflow_id,
        version,
        nodes,
        edges,
        payload.revision,
        force,
    )
    return mapper.to_graph_out(view)


@router.post(
    "/{workflow_id}/versions/{version}/validate",
    response_model=ValidateOut,
    summary="校验 Graph",
)
@declares(SELF)
def validate_graph(
    workflow_id: str, version: int, request: Request, payload: GraphIn | None = None
) -> ValidateOut:
    nodes = None
    edges = None
    if payload is not None:
        nodes, edges = mapper.graph_in(payload)
    return mapper.to_validate_out(
        _service(request).validate_graph(workflow_id, version, nodes, edges)
    )


@router.post(
    "/{workflow_id}/versions/{version}/clone",
    response_model=VersionOut,
    status_code=201,
    summary="派生新版本",
)
@declares(Capability.WORKFLOW_MODIFY)
def clone_version(workflow_id: str, version: int, request: Request) -> VersionOut:
    view = _service(request).clone_version(get_actor(request), workflow_id, version)
    return mapper.to_contract_version_out(view)


@router.post(
    "/{workflow_id}/versions/{version}/publish",
    response_model=VersionOut,
    summary="发布版本",
)
@declares(Capability.WORKFLOW_PUBLISH)
def publish_version(workflow_id: str, version: int, request: Request) -> VersionOut:
    view = _service(request).publish_version(get_actor(request), workflow_id, version)
    return mapper.to_contract_version_out(view)


# ---- 旧别名：保留实现，但不进入契约 ----


@router.patch(
    "/{workflow_id}",
    response_model=LegacyWorkflowOut,
    summary="重命名流程（旧别名）",
    deprecated=True,
    include_in_schema=False,
)
@declares(Capability.WORKFLOW_MODIFY)
def rename_workflow(
    workflow_id: str, payload: LegacyWorkflowIn, request: Request
) -> LegacyWorkflowOut:
    view = _service(request).rename_definition(
        get_actor(request), workflow_id, mapper.workflow_command(payload)
    )
    return mapper.to_workflow_out(view)


@router.post(
    "/{workflow_id}/versions",
    response_model=LegacyVersionOut,
    status_code=201,
    summary="新增草稿版本（旧别名）",
    deprecated=True,
    include_in_schema=False,
)
@declares(Capability.WORKFLOW_MODIFY)
def add_version(
    workflow_id: str, payload: VersionIn, request: Request
) -> LegacyVersionOut:
    view = _service(request).add_version(
        get_actor(request), workflow_id, mapper.version_command(payload)
    )
    return mapper.to_version_out(view)
