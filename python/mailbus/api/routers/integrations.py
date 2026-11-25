"""集成与运行配置路由：清单、插件、调用调试、env 与重载。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from mailbus.api.deps import declares, get_actor
from mailbus.api.schemas.contract.system import IntegrationInvokeOut
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
    actor = get_actor(request)
    result = _service(request).mutate_plugins(actor, payload.action, payload.spec)
    return PluginActionOut(**result)


@router.post(
    "/settings/integrations/{name}/invoke",
    response_model=IntegrationInvokeOut,
    summary="调用集成动作",
)
@declares(Capability.SYSTEM_CONFIG)
def invoke(
    name: str, payload: IntegrationInvokeIn, request: Request
) -> IntegrationInvokeOut:
    actor = get_actor(request)
    result = _service(request).invoke(actor, name, payload.action, payload.params)
    return IntegrationInvokeOut(
        name=name, action=payload.action,
        result={key: value for key, value in result.items() if key not in ("name", "action")},
    )


@router.get("/settings/env", response_model=EnvGroupsOut, summary="运行配置")
def env_groups(request: Request) -> EnvGroupsOut:
    get_actor(request)
    return EnvGroupsOut(**_service(request).env_groups())


@router.post("/settings/env", response_model=EnvGroupsOut, summary="写入运行配置")
@declares(Capability.SYSTEM_CONFIG)
def update_env(payload: EnvUpdateIn, request: Request) -> EnvGroupsOut:
    actor = get_actor(request)
    return EnvGroupsOut(**_service(request).update_env(actor, payload.vars))


@router.post("/dev/reload", response_model=ReloadOut, summary="重载插件")
@declares(Capability.SYSTEM_CONFIG)
def reload_plugins(request: Request) -> ReloadOut:
    return ReloadOut(**_service(request).reload(get_actor(request)))
