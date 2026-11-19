"""技能包上下文对外的仓储与来源端口。"""

from __future__ import annotations

from typing import Protocol, Self

from mailbus.core.agents.ports import AgentRepository
from mailbus.core.identity.ports import EmployeeRepository
from mailbus.core.shared.ports import OutboxPort
from mailbus.core.skills.models import SkillBinding, SkillPackage, SkillProbe
from mailbus.core.skills.values import SkillSourceType, SkillTargetType


class SkillPackageRepository(Protocol):
    def get(self, package_id: str) -> SkillPackage | None: ...

    def save(self, package: SkillPackage) -> None: ...

    def delete(self, package_id: str) -> None: ...

    def list_all(self) -> list[SkillPackage]: ...


class SkillBindingRepository(Protocol):
    def upsert(self, binding: SkillBinding) -> None: ...

    def delete(
        self, package_id: str, target_type: SkillTargetType, target_id: str
    ) -> None: ...

    def list_by_target(
        self, target_type: SkillTargetType, target_id: str
    ) -> list[SkillBinding]: ...

    def list_all(self) -> list[SkillBinding]: ...


class SkillSourcePort(Protocol):
    def probe(
        self, source_type: SkillSourceType, source_uri: str, entry: str
    ) -> SkillProbe:
        """探测来源是否可达并读取版本；失败返回 error，不抛异常。"""


class SkillsUnitOfWork(Protocol):
    outbox: OutboxPort
    packages: SkillPackageRepository
    bindings: SkillBindingRepository
    employees: EmployeeRepository
    agents: AgentRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...

    def commit(self) -> None: ...
