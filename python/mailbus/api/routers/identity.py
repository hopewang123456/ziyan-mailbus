"""identity 路由：只做协议转换，业务与事务在 application。"""

from __future__ import annotations

import ipaddress
from typing import Literal

from fastapi import APIRouter, Request, Response

from mailbus.api.deps import PUBLIC, SELF, declares, get_actor, get_token
from mailbus.api.mappers import identity as mapper
from mailbus.api.mappers import org as org_mapper
from mailbus.api.schemas.identity import (
    BootstrapStatusOut,
    EmployeeOut,
    ModelConfigIn,
    SessionOut,
    SuperAdminIn,
)
from mailbus.api.schemas.org import TeamIn, TeamOut
from mailbus.core.shared.errors import PermissionDeniedError, RateLimitedError
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/identity", tags=["identity"])

# TestClient 的默认来源为 "testclient"，视为本机调用。
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})
# 容器/局域网部署的来源是私网地址，仍视为可信；公网来源拒绝。
_TRUSTED_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    )
)


def _is_trusted_source(host: str) -> bool:
    if host in _LOOPBACK_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in net for net in _TRUSTED_NETWORKS)


def _guard_bootstrap_source(request: Request) -> None:
    """M13：首启仅允许本机/私网来源，避免公网暴露时超管被抢注。

    跨公网初始化场景可用 MAILBUS_BOOTSTRAP_ALLOW_REMOTE=1 放开。
    """
    if request.app.state.container.settings.bootstrap_allow_remote:
        return
    host = request.client.host if request.client else ""
    if not _is_trusted_source(host):
        raise PermissionDeniedError("首次初始化仅允许本机或内网访问")


def _services(request: Request):
    return request.app.state.container.identity


def _rate_limit(request: Request, limiter, key: str) -> None:
    """匿名写接口按客户端 IP 限流，超限返回 429。"""
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(f"{key}:{client}"):
        raise RateLimitedError("请求过于频繁，请稍后重试")


@router.get("/bootstrap", response_model=BootstrapStatusOut, summary="引导向导进度")
def get_bootstrap(request: Request) -> BootstrapStatusOut:
    return mapper.to_bootstrap_out(_services(request).bootstrap.status())


@router.post(
    "/bootstrap/super-admin", response_model=SessionOut, status_code=201, summary="创建超级管理员"
)
@declares(PUBLIC)
def create_super_admin(payload: SuperAdminIn, request: Request) -> SessionOut:
    _guard_bootstrap_source(request)
    _rate_limit(
        request,
        request.app.state.container.public_bootstrap_limiter,
        "identity.bootstrap.super_admin",
    )
    result = _services(request).bootstrap.create_super_admin(
        mapper.super_admin_command(payload)
    )
    return mapper.to_session_out(result)


@router.post(
    "/bootstrap/model-config", response_model=BootstrapStatusOut, summary="配置模型"
)
@declares(Capability.SYSTEM_CONFIG)
def configure_model(payload: ModelConfigIn, request: Request) -> BootstrapStatusOut:
    status = _services(request).bootstrap.configure_model(
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


@router.get(
    "/staff",
    response_model=list[EmployeeOut],
    summary="员工列表（旧别名）",
    deprecated=True,
    include_in_schema=False,
)
def list_staff(
    request: Request, status: Literal["pending", "active", "all"] = "pending"
) -> list[EmployeeOut]:
    views = _services(request).staff.list_staff(get_actor(request), status)
    return [mapper.to_employee_out(view) for view in views]


@router.post(
    "/staff/{employee_id}/heartbeat",
    response_model=EmployeeOut,
    summary="上报心跳（旧别名）",
    deprecated=True,
    include_in_schema=False,
)
@declares(SELF)
def heartbeat_staff(employee_id: str, request: Request) -> EmployeeOut:
    view = _services(request).staff.heartbeat(get_actor(request), employee_id)
    return mapper.to_employee_out(view)


@router.get("/me", response_model=EmployeeOut, summary="当前登录员工")
def get_me(request: Request) -> EmployeeOut:
    return mapper.to_employee_out(_services(request).staff.me(get_actor(request)))


@router.post("/logout", status_code=204, summary="退出当前会话")
@declares(SELF)
def logout(request: Request) -> Response:
    _services(request).sessions.resolve(get_token(request))
    _services(request).sessions.logout(get_token(request))
    return Response(status_code=204)
