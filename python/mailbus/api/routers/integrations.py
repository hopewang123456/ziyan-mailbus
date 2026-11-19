"""集成与运行配置路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from mailbus.api.deps import declares, get_actor
from mailbus.api.schemas.integrations import (
    EnvGroupsOut,
    EnvUpdateIn,
    IntegrationsOut,
    IntegrationInvokeIn,
    PluginActionIn,
    PluginActionOut,
    ReloadOut,
)
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api", tags=["integration"])


def _service(request: Request):
    return request.app.state.container.integrations


@router.get(
    "/settings/integrations", response_model=IntegrationsOut, summary="集成清单"
)
def list_integrations(request: Request) -> IntegrationsOut:
    get_actor(request)
    return IntegrationsOut(**_service(request).list_integrations())


@router.post(
    "/settings/integrations", response_model=PluginActionOut, summary="增删插件"
)
@declares(Capability.SYSTEM_CONFIG)
def mutate_plugins(payload: PluginActionIn, request: Request) -> PluginActionOut:
    result = _service(request).mutate_plugins(
        get_actor(request), payload.action, payload.spec
    )
    return PluginActionOut(**result)


@router.post(
    "/settings/integrations/{name}/invoke",
    response_model=dict[str, Any],
    summary="调用集成动作",
)
@declares(Capability.SYSTEM_CONFIG)
def invoke(
    name: str, payload: IntegrationInvokeIn, request: Request
) -> dict[str, Any]:
    return _service(request).invoke(
        get_actor(request), name, payload.action, payload.params
    )


@router.get("/settings/env", response_model=EnvGroupsOut, summary="运行配置")
def env_groups(request: Request) -> EnvGroupsOut:
    get_actor(request)
    return EnvGroupsOut(**_service(request).env_groups())


@router.post("/settings/env", response_model=EnvGroupsOut, summary="写入运行配置")
@declares(Capability.SYSTEM_CONFIG)
def update_env(payload: EnvUpdateIn, request: Request) -> EnvGroupsOut:
    return EnvGroupsOut(
        **_service(request).update_env(get_actor(request), payload.vars)
    )


@router.post("/dev/reload", response_model=ReloadOut, summary="重载插件（占位）")
@declares(Capability.SYSTEM_CONFIG)
def reload_plugins(request: Request) -> ReloadOut:
    return ReloadOut(**_service(request).reload(get_actor(request)))
