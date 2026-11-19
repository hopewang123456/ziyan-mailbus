"""技能包路由：登记、更新、探测、删除与绑定解析。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import skills as mapper
from mailbus.api.schemas.skills import (
    EffectiveSkillOut,
    SkillBindingIn,
    SkillPackageIn,
    SkillPackageOut,
    SkillPackageUpdateIn,
)
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/skills", tags=["skill"])


def _service(request: Request):
    return request.app.state.container.skills


@router.get("", response_model=list[SkillPackageOut], summary="技能包列表")
def list_skills(request: Request) -> list[SkillPackageOut]:
    get_actor(request)
    return [mapper.to_package_out(view) for view in _service(request).list_all()]


@router.get(
    "/effective", response_model=list[EffectiveSkillOut], summary="有效技能解析"
)
def effective_skills(
    request: Request,
    target_type: Literal["agent", "employee"],
    target_id: str,
) -> list[EffectiveSkillOut]:
    get_actor(request)
    views = request.app.state.container.skill_effective.get(target_type, target_id)
    return [mapper.to_effective_out(view) for view in views]


@router.post("", response_model=SkillPackageOut, status_code=201, summary="登记技能包")
@declares(Capability.SYSTEM_CONFIG)
def create_skill(payload: SkillPackageIn, request: Request) -> SkillPackageOut:
    view = _service(request).create(
        get_actor(request), mapper.package_command(payload)
    )
    return mapper.to_package_out(view)


@router.patch(
    "/{package_id}", response_model=SkillPackageOut, summary="更新技能包"
)
@declares(Capability.SYSTEM_CONFIG)
def update_skill(
    package_id: str, payload: SkillPackageUpdateIn, request: Request
) -> SkillPackageOut:
    view = _service(request).update(
        get_actor(request), package_id, mapper.update_command(payload)
    )
    return mapper.to_package_out(view)


@router.post(
    "/{package_id}/refresh", response_model=SkillPackageOut, summary="探测技能包来源"
)
@declares(Capability.SYSTEM_CONFIG)
def refresh_skill(package_id: str, request: Request) -> SkillPackageOut:
    view = _service(request).refresh(get_actor(request), package_id)
    return mapper.to_package_out(view)


@router.post("/{package_id}/delete", status_code=204, summary="删除技能包")
@declares(Capability.SYSTEM_CONFIG)
def delete_skill(package_id: str, request: Request) -> Response:
    _service(request).delete(get_actor(request), package_id)
    return Response(status_code=204)


@router.post(
    "/{package_id}/bindings", response_model=SkillPackageOut, summary="变更技能绑定"
)
@declares(Capability.SYSTEM_CONFIG)
def bind_skill(
    package_id: str, payload: SkillBindingIn, request: Request
) -> SkillPackageOut:
    view = _service(request).bind(
        get_actor(request), package_id, mapper.binding_command(payload)
    )
    return mapper.to_package_out(view)
