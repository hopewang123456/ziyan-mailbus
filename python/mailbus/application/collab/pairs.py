"""结对用例：创建、列表与结束。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from mailbus.application.identity.dto import Actor
from mailbus.core.collab.models import Pair
from mailbus.core.collab.ports import CollabEventBus, CollabUnitOfWork
from mailbus.core.identity.policy import ensure_active
from mailbus.core.shared.errors import (
    InvalidStateError,
    NotFoundError,
    PermissionDeniedError,
)
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability


@dataclass(frozen=True, slots=True)
class PairView:
    pair_id: str
    initiator_id: str
    partner_id: str
    state: str
    created_at: datetime
    ended_at: datetime | None


class PairService:
    def __init__(
        self,
        uow_factory: Callable[[], CollabUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        events: CollabEventBus,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._events = events

    def list_pairs(
        self,
        actor: Actor,
        *,
        state: str | None = None,
        limit: int = 100,
    ) -> tuple[PairView, ...]:
        viewer_id = None if Capability.ALL in actor.capabilities else actor.employee_id
        with self._uow() as uow:
            pairs = uow.pairs.list_pairs(
                state=state, viewer_id=viewer_id, limit=limit
            )
        return tuple(_view(pair) for pair in pairs)

    def active_pairs(self) -> tuple[PairView, ...]:
        """布局投影用：全部进行中的结对，不做可见范围过滤。"""
        with self._uow() as uow:
            pairs = uow.pairs.list_pairs(state="active", limit=500)
        return tuple(_view(pair) for pair in pairs)

    def create(self, actor: Actor, partner_id: str) -> PairView:
        ensure_active(actor.to_subject())
        partner = partner_id.strip()
        if partner == actor.employee_id:
            raise InvalidStateError("不能与自己结对")
        now = self._clock.now()
        with self._uow() as uow:
            if uow.employees.get(partner) is None:
                raise NotFoundError("员工不存在")
            existing = uow.pairs.find_active_between(actor.employee_id, partner)
            if existing is not None:
                raise InvalidStateError("双方已存在进行中的结对")
            pair = Pair(
                pair_id=self._ids.new("pair"),
                initiator_id=actor.employee_id,
                partner_id=partner,
                state="active",
                created_at=now,
            )
            uow.pairs.save(pair)
            uow.commit()
        self._events.publish(
            "pair.started",
            {
                "pair_id": pair.pair_id,
                "initiator_id": pair.initiator_id,
                "partner_id": pair.partner_id,
                "at": now.isoformat(),
            },
        )
        return _view(pair)

    def end(self, actor: Actor, pair_id: str) -> None:
        ensure_active(actor.to_subject())
        now = self._clock.now()
        with self._uow() as uow:
            pair = uow.pairs.get(pair_id)
            if pair is None:
                raise NotFoundError("结对不存在")
            if Capability.ALL not in actor.capabilities and not pair.involves(
                actor.employee_id
            ):
                raise PermissionDeniedError("只能结束自己参与的结对")
            if pair.state == "ended":
                return
            ended = Pair(
                pair_id=pair.pair_id,
                initiator_id=pair.initiator_id,
                partner_id=pair.partner_id,
                state="ended",
                created_at=pair.created_at,
                ended_at=now,
            )
            uow.pairs.save(ended)
            uow.commit()
        self._events.publish(
            "pair.ended",
            {"pair_id": pair_id, "at": now.isoformat()},
        )


def _view(pair: Pair) -> PairView:
    return PairView(
        pair_id=pair.pair_id,
        initiator_id=pair.initiator_id,
        partner_id=pair.partner_id,
        state=pair.state,
        created_at=pair.created_at,
        ended_at=pair.ended_at,
    )
