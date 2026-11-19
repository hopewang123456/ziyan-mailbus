"""identity 路由：只做协议转换，业务与事务在 application。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response

from mailbus.api.deps import PUBLIC, SELF, declares, get_actor, get_token
from mailbus.api.mappers import identity as mapper
from mailbus.api.mappers import org as org_mapper
from mailbus.api.schemas.identity import (
    AgentBindIn,
    ApplyIn,
    ApplyOut,
    BootstrapStatusOut,
    DeregisterIn,
    EmployeeOut,
    EndpointReviewIn,
    InviteIn,
    InviteOut,
    ManagerIn,
    ModelConfigIn,
    ReviewIn,
    SeatAssignIn,
    SessionOut,
    SuperAdminIn,
)
from mailbus.api.schemas.org import TeamIn, TeamOut
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/identity", tags=["identity"])


def _services(request: Request):
    return request.app.state.container.identity


@router.get("/bootstrap", response_model=BootstrapStatusOut, summary="引导向导进度")
def get_bootstrap(request: Request) -> BootstrapStatusOut:
    return mapper.to_bootstrap_out(_services(request).bootstrap.status())


@router.post(
    "/bootstrap/super-admin", response_model=SessionOut, status_code=201, summary="创建超级管理员"
)
@declares(PUBLIC)
def create_super_admin(payload: SuperAdminIn, request: Request) -> SessionOut:
    result = _services(request).bootstrap.create_super_admin(mapper.super_admin_command(payload))
    return mapper.to_session_out(result)


@router.post(
    "/bootstrap/model-config", response_model=BootstrapStatusOut, summary="配置模型"
)
@declares(Capability.SYSTEM_CONFIG)
def configure_model(payload: ModelConfigIn, request: Request) -> BootstrapStatusOut:
    services = _services(request)
    status = services.bootstrap.configure_model(
        get_actor(request), mapper.model_config_command(payload)
    )
    return mapper.to_bootstrap_out(status)


@router.post("/bootstrap/team", response_model=TeamOut, summary="创建首个团队")
@declares(Capability.SYSTEM_CONFIG)
def create_team(payload: TeamIn, request: Request) -> TeamOut:
    team = _services(request).bootstrap.create_team(
        get_actor(request), org_mapper.team_command(payload)
    )
    return org_mapper.to_team_out(team)


@router.post(
    "/bootstrap/{step}/skip", response_model=BootstrapStatusOut, summary="跳过引导步骤"
)
@declares(Capability.SYSTEM_CONFIG)
def skip_bootstrap_step(step: str, request: Request) -> BootstrapStatusOut:
    status = _services(request).bootstrap.skip(get_actor(request), step)
    return mapper.to_bootstrap_out(status)


@router.get("/staff", response_model=list[EmployeeOut], summary="员工列表")
def list_staff(
    request: Request, status: Literal["pending", "active", "all"] = "pending"
) -> list[EmployeeOut]:
    views = _services(request).staff.list_staff(get_actor(request), status)
    return [mapper.to_employee_out(view) for view in views]


@router.post("/staff", response_model=ApplyOut, status_code=201, summary="提交入伙申请")
@declares(PUBLIC)
def apply_staff(payload: ApplyIn, request: Request) -> ApplyOut:
    result = _services(request).staff.apply(mapper.apply_command(payload))
    return mapper.to_apply_out(result)


@router.get("/staff/{employee_id}", response_model=EmployeeOut, summary="员工详情")
def get_staff(employee_id: str, request: Request) -> EmployeeOut:
    return mapper.to_employee_out(
        _services(request).staff.get(get_actor(request), employee_id)
    )


@router.post("/staff/{employee_id}/review", response_model=EmployeeOut, summary="审核申请")
@declares(Capability.EMPLOYEE_INVITE)
def review_staff(employee_id: str, payload: ReviewIn, request: Request) -> EmployeeOut:
    view = _services(request).staff.review(
        get_actor(request), employee_id, mapper.review_command(payload)
    )
    return mapper.to_employee_out(view)


@router.post("/staff/{employee_id}/activate", response_model=SessionOut, summary="激活账号")
@declares(Capability.EMPLOYEE_INVITE)
def activate_staff(employee_id: str, request: Request) -> SessionOut:
    result = _services(request).staff.activate(get_actor(request), employee_id)
    return mapper.to_session_out(result)


@router.post("/staff/{employee_id}/heartbeat", response_model=EmployeeOut, summary="上报心跳")
@declares(SELF)
def heartbeat_staff(employee_id: str, request: Request) -> EmployeeOut:
    view = _services(request).staff.heartbeat(get_actor(request), employee_id)
    return mapper.to_employee_out(view)


@router.post(
    "/staff/{employee_id}/deregister", response_model=EmployeeOut, summary="注销账号"
)
@declares(Capability.EMPLOYEE_REMOVE)
def deregister_staff(employee_id: str, payload: DeregisterIn, request: Request) -> EmployeeOut:
    view = _services(request).staff.deregister(
        get_actor(request), employee_id, payload.reason
    )
    return mapper.to_employee_out(view)


@router.patch(
    "/staff/{employee_id}/seat", response_model=EmployeeOut, summary="分配或释放工位"
)
@declares(Capability.ORG_MANAGE)
def assign_seat(
    employee_id: str, payload: SeatAssignIn, request: Request
) -> EmployeeOut:
    view = _services(request).staff.set_seat(
        get_actor(request), employee_id, payload.seat_id
    )
    return mapper.to_employee_out(view)


@router.patch(
    "/staff/{employee_id}/agent", response_model=EmployeeOut, summary="绑定或解绑 Agent"
)
@declares(Capability.ORG_MANAGE)
def bind_agent(
    employee_id: str, payload: AgentBindIn, request: Request
) -> EmployeeOut:
    view = _services(request).staff.set_agent(
        get_actor(request), employee_id, payload.agent_id
    )
    return mapper.to_employee_out(view)


@router.patch(
    "/staff/{employee_id}/endpoint", response_model=EmployeeOut, summary="审核 Agent 端点"
)
@declares(Capability.SYSTEM_CONFIG)
def review_endpoint(
    employee_id: str, payload: EndpointReviewIn, request: Request
) -> EmployeeOut:
    view = _services(request).staff.review_endpoint(
        get_actor(request), employee_id, payload.approved
    )
    return mapper.to_employee_out(view)


@router.patch(
    "/staff/{employee_id}/manager", response_model=EmployeeOut, summary="指定或取消管理者"
)
@declares(Capability.SYSTEM_CONFIG)
def set_manager(
    employee_id: str, payload: ManagerIn, request: Request
) -> EmployeeOut:
    view = _services(request).staff.set_manager(
        get_actor(request), employee_id, payload.enabled
    )
    return mapper.to_employee_out(view)


@router.post("/invites", response_model=InviteOut, status_code=201, summary="签发邀请码")
@declares(Capability.EMPLOYEE_INVITE)
def issue_invite(payload: InviteIn, request: Request) -> InviteOut:
    view = _services(request).invites.issue(
        get_actor(request), mapper.invite_command(payload)
    )
    return mapper.to_invite_out(view)


@router.get("/me", response_model=EmployeeOut, summary="当前登录员工")
def get_me(request: Request) -> EmployeeOut:
    return mapper.to_employee_out(_services(request).staff.me(get_actor(request)))


@router.post("/logout", status_code=204, summary="退出当前会话")
@declares(SELF)
def logout(request: Request) -> Response:
    _services(request).sessions.resolve(get_token(request))
    _services(request).sessions.logout(get_token(request))
    return Response(status_code=204)
