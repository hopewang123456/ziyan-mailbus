"""技能包用例：登记、更新、探测、删除与绑定。

本期只登记与探测来源；不复制文件、不安装依赖、不执行技能。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor
from mailbus.application.skills.dto import (
    SkillBindingCommand,
    SkillBindingView,
    SkillPackageCommand,
    SkillPackageView,
    SkillUpdateCommand,
    binding_view,
)
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.shared.errors import NotFoundError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability
from mailbus.core.skills import rules
from mailbus.core.skills.models import SkillBinding, SkillPackage
from mailbus.core.skills.ports import SkillSourcePort, SkillsUnitOfWork
from mailbus.core.skills.values import SkillTargetType


class SkillService:
    def __init__(
        self,
        uow_factory: Callable[[], SkillsUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        source: SkillSourcePort,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._source = source

    def create(self, actor: Actor, cmd: SkillPackageCommand) -> SkillPackageView:
        self._require(actor)
        now = self._clock.now()
        with self._uow() as uow:
            package, events = rules.create_package(
                self._ids.new("skill"),
                name=cmd.name,
                source_type=cmd.source_type,
                source_uri=cmd.source_uri,
                entry=cmd.entry,
                note=cmd.note,
                now=now,
            )
            uow.packages.save(package)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return SkillPackageView.of(package)

    def update(
        self, actor: Actor, package_id: str, cmd: SkillUpdateCommand
    ) -> SkillPackageView:
        self._require(actor)
        now = self._clock.now()
        with self._uow() as uow:
            package = self._load(uow, package_id)
            updated, events = rules.update_package(package, cmd.changes, now)
            uow.packages.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
            bindings = uow.bindings.list_all()
        return SkillPackageView.of(updated, _bindings_of(package_id, bindings))

    def refresh(self, actor: Actor, package_id: str) -> SkillPackageView:
        """探测来源；网络/文件读取在事务之外进行，避免长事务。"""
        self._require(actor)
        with self._uow() as uow:
            package = self._load(uow, package_id)
        probe = self._source.probe(
            package.source_type, package.source_uri, package.entry
        )
        now = self._clock.now()
        with self._uow() as uow:
            updated, events = rules.apply_probe(self._load(uow, package_id), probe, now)
            uow.packages.save(updated)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
            bindings = uow.bindings.list_all()
        return SkillPackageView.of(updated, _bindings_of(package_id, bindings))

    def delete(self, actor: Actor, package_id: str) -> None:
        self._require(actor)
        now = self._clock.now()
        with self._uow() as uow:
            package = self._load(uow, package_id)
            events = rules.delete_package(package, now)
            uow.packages.delete(package_id)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()

    def list_all(self) -> tuple[SkillPackageView, ...]:
        with self._uow() as uow:
            packages = uow.packages.list_all()
            bindings = uow.bindings.list_all()
        return tuple(
            SkillPackageView.of(package, _bindings_of(package.package_id, bindings))
            for package in packages
        )

    def bind(
        self, actor: Actor, package_id: str, cmd: SkillBindingCommand
    ) -> SkillPackageView:
        self._require(actor)
        now = self._clock.now()
        with self._uow() as uow:
            package = self._load(uow, package_id)
            self._ensure_target(uow, cmd)
            binding, events = rules.make_binding(
                package_id, cmd.target_type, cmd.target_id, cmd.enabled, now
            )
            uow.bindings.upsert(binding)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
            bindings = uow.bindings.list_all()
        return SkillPackageView.of(package, _bindings_of(package_id, bindings))

    @staticmethod
    def _require(actor: Actor) -> None:
        ensure_allowed(
            actor.to_subject(), Capability.SYSTEM_CONFIG, Resource(kind="skill")
        )

    @staticmethod
    def _load(uow: SkillsUnitOfWork, package_id: str) -> SkillPackage:
        package = uow.packages.get(package_id)
        if package is None:
            raise NotFoundError("技能包不存在")
        return package

    @staticmethod
    def _ensure_target(uow: SkillsUnitOfWork, cmd: SkillBindingCommand) -> None:
        if cmd.target_type is SkillTargetType.AGENT:
            exists = uow.agents.get(cmd.target_id) is not None
            label = "Agent"
        else:
            exists = uow.employees.get(cmd.target_id) is not None
            label = "员工"
        if not exists:
            raise NotFoundError(f"{label}不存在")


def _bindings_of(
    package_id: str, bindings: Iterable[SkillBinding]
) -> tuple[SkillBindingView, ...]:
    return tuple(
        binding_view(binding)
        for binding in bindings
        if binding.package_id == package_id
    )
