"""首次部署三步向导：超管 → 模型配置 → 首团队。

步骤可跳过（超管除外），重复调用幂等；超管创建后其余步骤必须由具备
system_config 能力的账号执行。首团队由组织上下文创建，这里只负责推进向导。
"""

from __future__ import annotations

from collections.abc import Callable

from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import (
    Actor,
    BootstrapStatusView,
    BootstrapStepView,
    ModelConfigCommand,
    SessionResult,
    SuperAdminCommand,
    employee_view,
)
from mailbus.application.identity.sessions import issue_session
from mailbus.application.org.dto import TeamCommand, TeamView
from mailbus.application.org.service import OrgService
from mailbus.core.identity import rules
from mailbus.core.identity.models import Registration
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.identity.ports import IdentityUnitOfWork
from mailbus.core.identity.values import (
    BOOTSTRAP_STEPS,
    SKIPPABLE_STEPS,
    AccountType,
    BootstrapStep,
)
from mailbus.core.shared.errors import IdempotencyConflictError, InvalidStateError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability, DataScope


def _status_of(done: dict[str, dict]) -> BootstrapStatusView:
    steps = tuple(
        BootstrapStepView(
            step=step.value,
            done=step.value in done,
            skippable=step in SKIPPABLE_STEPS,
        )
        for step in BOOTSTRAP_STEPS
    )
    return BootstrapStatusView(steps=steps, completed=all(step.done for step in steps))


class BootstrapService:
    def __init__(
        self,
        uow_factory: Callable[[], IdentityUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        org: OrgService,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._org = org

    def status(self) -> BootstrapStatusView:
        with self._uow() as uow:
            done = uow.bootstrap.completed()
        return _status_of(done)

    def create_super_admin(self, cmd: SuperAdminCommand) -> SessionResult:
        now = self._clock.now()
        with self._uow() as uow:
            done = uow.bootstrap.completed()
            if BootstrapStep.SUPER_ADMIN.value in done:
                raise IdempotencyConflictError("超级管理员已创建")
            employee_id = cmd.employee_id or self._ids.new("emp")
            registration = Registration(
                employee_id=employee_id,
                display_name=cmd.display_name,
                account_type=AccountType.HUMAN,
                capabilities=frozenset({Capability.ALL}),
                data_scope=DataScope.GLOBAL,
                approved=True,
            )
            employee, submitted = rules.submit(registration, now)
            employee, activated = rules.activate(employee, now)
            uow.employees.save(employee)
            uow.bootstrap.mark(
                BootstrapStep.SUPER_ADMIN.value, {"employee_id": employee_id}, now
            )
            token = issue_session(uow, employee, self._ids, now)
            enqueue_events(uow.outbox, (*submitted, *activated), self._ids, now)
            uow.commit()
        return SessionResult(employee=employee_view(employee), token=token)

    def configure_model(self, actor: Actor, cmd: ModelConfigCommand) -> BootstrapStatusView:
        self._require_admin(actor)
        now = self._clock.now()
        with self._uow() as uow:
            uow.bootstrap.mark(
                BootstrapStep.MODEL_CONFIG.value,
                {"provider": cmd.provider, "model": cmd.model, "api_base": cmd.api_base},
                now,
            )
            uow.commit()
        return self.status()

    def create_team(self, actor: Actor, cmd: TeamCommand) -> TeamView:
        self._require_admin(actor)
        with self._uow() as uow:
            detail = uow.bootstrap.completed().get(BootstrapStep.FIRST_TEAM.value, {})
        existing_id = detail.get("team_id")
        if existing_id:
            existing = self._org.get_team(existing_id)
            if existing is not None:
                return existing
        team = self._org.create_team(
            actor,
            TeamCommand(name=cmd.name, team_id=cmd.team_id or self._ids.new("team")),
        )
        now = self._clock.now()
        with self._uow() as uow:
            uow.bootstrap.mark(
                BootstrapStep.FIRST_TEAM.value,
                {"team_id": team.team_id, "name": team.name},
                now,
            )
            uow.commit()
        return team

    def skip(self, actor: Actor, step_name: str) -> BootstrapStatusView:
        self._require_admin(actor)
        step = _parse_step(step_name)
        if step not in SKIPPABLE_STEPS:
            raise InvalidStateError("超级管理员步骤不可跳过")
        now = self._clock.now()
        with self._uow() as uow:
            if step.value not in uow.bootstrap.completed():
                uow.bootstrap.mark(step.value, {"skipped": True}, now)
            uow.commit()
        return self.status()

    def _require_admin(self, actor: Actor) -> None:
        ensure_allowed(actor.to_subject(), Capability.SYSTEM_CONFIG, Resource(kind="system"))


def _parse_step(step_name: str) -> BootstrapStep:
    try:
        return BootstrapStep(step_name)
    except ValueError as exc:
        raise InvalidStateError(f"未知引导步骤：{step_name}") from exc
