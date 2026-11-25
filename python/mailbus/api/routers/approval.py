"""approval 路由：HITL 审批请求与裁决。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import approval as mapper
from mailbus.api.schemas.approval import ApprovalIn, ApprovalOut
from mailbus.api.schemas.contract.task import ApprovalListOut, ResolveIn
from mailbus.application.approval.dto import ApprovalView
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/approvals", tags=["approval"])


def _service(request: Request):
    return request.app.state.container.approvals


def _engine(request: Request):
    return request.app.state.container.task_engine


@router.get("", response_model=ApprovalListOut, summary="审批列表")
def list_approvals(
    request: Request,
    state: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ApprovalListOut:
    items, total = _engine(request).list_approvals(get_actor(request), state, limit, offset)
    return ApprovalListOut(
        items=[mapper.to_approval_out(ApprovalView.of(item)) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ApprovalOut, status_code=201, summary="发起审批")
@declares(Capability.HITL_REQUEST)
def request_approval(payload: ApprovalIn, request: Request) -> ApprovalOut:
    view = _service(request).request(get_actor(request), mapper.approval_command(payload))
    return mapper.to_approval_out(view)


@router.get("/{approval_id}", response_model=ApprovalOut, summary="审批详情")
def get_approval(approval_id: str, request: Request) -> ApprovalOut:
    actor = get_actor(request)
    return mapper.to_approval_out(_service(request).get(actor, approval_id))


@router.post(
    "/{approval_id}/resolve", response_model=ApprovalOut, summary="裁决审批"
)
@declares(Capability.HITL_RESOLVE)
def resolve_approval(
    approval_id: str, payload: ResolveIn, request: Request
) -> ApprovalOut:
    item = _engine(request).resolve_approval(
        get_actor(request), approval_id, payload.decision, payload.comment)
    return mapper.to_approval_out(ApprovalView.of(item))


@router.delete("/{approval_id}", status_code=204, summary="撤回审批")
@declares(Capability.HITL_REQUEST)
def withdraw_approval(approval_id: str, request: Request) -> Response:
    _service(request).withdraw(get_actor(request), approval_id)
    return Response(status_code=204)
