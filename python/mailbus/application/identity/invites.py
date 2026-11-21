"""邀请码签发（消费在员工申请用例中完成）。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from mailbus.application.events import enqueue_events
from mailbus.application.identity import inheritance
from mailbus.application.identity.dto import Actor, InviteCommand, InviteView, invite_view
from mailbus.core.identity.models import Invite
from mailbus.core.identity.policy import (
    Resource,
    can_grant_capabilities,
    ensure_allowed,
    scope_is_within,
)
from mailbus.core.identity.ports import IdentityUnitOfWork
from mailbus.core.shared.errors import PermissionDeniedError
from mailbus.core.shared.events import DomainEvent
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability


class InviteService:
    def __init__(
        self,
        uow_factory: Callable[[], IdentityUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids

    def issue(self, actor: Actor, cmd: InviteCommand) -> InviteView:
        ensure_allowed(
            actor.to_subject(),
            Capability.EMPLOYEE_INVITE,
            Resource(kind="invite", team_id=cmd.team_id),
        )
        if not scope_is_within(actor.data_scope, cmd.data_scope):
            raise PermissionDeniedError("不能授予超出自身范围的数据可见范围")
        now = self._clock.now()
        expires_at = now + timedelta(hours=cmd.expires_in_hours) if cmd.expires_in_hours else None
        with self._uow() as uow:
            # 最终授予能力 = 邀请显式能力 ∪ 岗位能力，两者都不得超出发起者自身范围。
            granted = inheritance.inherited_capabilities(
                uow, cmd.position_id, frozenset(cmd.capabilities)
            )
            if not can_grant_capabilities(actor.capabilities, granted):
                raise PermissionDeniedError("不能授予超出自身范围的能力")
            invite = Invite(
                invite_code=self._ids.new("inv"),
                account_type=cmd.account_type,
                team_id=cmd.team_id,
                position_id=cmd.position_id,
                data_scope=cmd.data_scope,
                capabilities=granted,
                created_by=actor.employee_id,
                created_at=now,
                expires_at=expires_at,
            )
            uow.invites.add(invite)
            enqueue_events(
                uow.outbox,
                (
                    DomainEvent(
                        kind="identity.invite_created",
                        payload={
                            "invite_code": invite.invite_code,
                            "created_by": actor.employee_id,
                        },
                    ),
                ),
                self._ids,
                now,
            )
            uow.commit()
        return invite_view(invite)
