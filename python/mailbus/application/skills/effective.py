"""有效技能解析：Agent 默认绑定 + 员工覆盖绑定。"""

from __future__ import annotations

from collections.abc import Callable

from mailbus.application.skills.dto import EffectiveSkillView
from mailbus.core.shared.errors import NotFoundError
from mailbus.core.skills.models import SkillBinding
from mailbus.core.skills.ports import SkillsUnitOfWork
from mailbus.core.skills.values import SkillTargetType


class SkillEffectiveQuery:
    def __init__(self, uow_factory: Callable[[], SkillsUnitOfWork]) -> None:
        self._uow = uow_factory

    def get(
        self, target_type: str, target_id: str
    ) -> tuple[EffectiveSkillView, ...]:
        target = SkillTargetType(target_type)
        with self._uow() as uow:
            agent_id = self._agent_id(uow, target, target_id)
            agent_rows = (
                uow.bindings.list_by_target(SkillTargetType.AGENT, agent_id)
                if agent_id
                else []
            )
            own_rows = (
                []
                if target is SkillTargetType.AGENT
                else uow.bindings.list_by_target(target, target_id)
            )
            packages = {item.package_id: item for item in uow.packages.list_all()}
        merged: dict[str, tuple[SkillBinding, str]] = {
            row.package_id: (row, "agent") for row in agent_rows
        }
        for row in own_rows:
            merged[row.package_id] = (row, target.value)
        views = [
            _view(packages[binding.package_id], binding, origin)
            for binding, origin in merged.values()
            if binding.package_id in packages
        ]
        return tuple(sorted(views, key=lambda item: item.name))

    @staticmethod
    def _agent_id(
        uow: SkillsUnitOfWork, target_type: SkillTargetType, target_id: str
    ) -> str | None:
        if target_type is SkillTargetType.AGENT:
            if uow.agents.get(target_id) is None:
                raise NotFoundError("Agent 不存在")
            return target_id
        employee = uow.employees.get(target_id)
        if employee is None:
            raise NotFoundError("员工不存在")
        return employee.agent_id


def _view(package, binding: SkillBinding, origin: str) -> EffectiveSkillView:
    return EffectiveSkillView(
        package_id=package.package_id,
        name=package.name,
        source_type=package.source_type.value,
        source_uri=package.source_uri,
        entry=package.entry,
        version=package.version,
        enabled=package.enabled and binding.enabled,
        note=package.note,
        origin=origin,
    )
