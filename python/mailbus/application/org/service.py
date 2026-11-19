"""组织用例：团队、岗位、工位覆盖。

写用例第一步做权限判定；读用例由 api 层要求登录后直接读取（不做范围过滤）。
"""

from __future__ import annotations

from collections.abc import Callable

from mailbus.application.events import enqueue_events
from mailbus.application.identity.dto import Actor
from mailbus.application.org.dto import (
    PositionCommand,
    PositionView,
    SeatCommand,
    SeatView,
    TeamCommand,
    TeamView,
    position_view,
    seat_view,
    team_view,
)
from mailbus.core.identity.policy import Resource, ensure_allowed
from mailbus.core.org import rules
from mailbus.core.org.models import LayoutDef, SeatAssignment
from mailbus.core.org.ports import LayoutSeedPort, OrgUnitOfWork
from mailbus.core.shared.errors import NotFoundError
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability


class OrgService:
    def __init__(
        self,
        uow_factory: Callable[[], OrgUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        seed: LayoutSeedPort,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._seed = seed

    def layout_seed(self) -> LayoutDef:
        return self._seed.load()

    def list_teams(self) -> tuple[TeamView, ...]:
        with self._uow() as uow:
            teams = uow.teams.list_all()
        return tuple(team_view(team) for team in teams)

    def get_team(self, team_id: str) -> TeamView | None:
        with self._uow() as uow:
            team = uow.teams.get(team_id)
        return None if team is None else team_view(team)

    def create_team(self, actor: Actor, cmd: TeamCommand) -> TeamView:
        ensure_allowed(
            actor.to_subject(), Capability.ORG_MANAGE, Resource(kind="team")
        )
        now = self._clock.now()
        team_id = cmd.team_id or self._ids.new("team")
        with self._uow() as uow:
            existing = uow.teams.get(team_id)
            if existing is not None:
                return team_view(existing)
            team, events = rules.create_team(team_id, cmd.name, now)
            uow.teams.create(team)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return team_view(team)

    def list_positions(self) -> tuple[PositionView, ...]:
        with self._uow() as uow:
            positions = uow.positions.list_all()
        return tuple(position_view(position) for position in positions)

    def create_position(self, actor: Actor, cmd: PositionCommand) -> PositionView:
        ensure_allowed(
            actor.to_subject(), Capability.ORG_MANAGE, Resource(kind="position")
        )
        now = self._clock.now()
        position_id = cmd.position_id or self._ids.new("pos")
        with self._uow() as uow:
            existing = uow.positions.get(position_id)
            if existing is not None:
                return position_view(existing)
            position, events = rules.create_position(
                position_id, cmd.name, frozenset(cmd.capabilities), now
            )
            uow.positions.add(position)
            enqueue_events(uow.outbox, events, self._ids, now)
            uow.commit()
        return position_view(position)

    def list_seats(self) -> tuple[SeatView, ...]:
        seed = self._seed.load()
        with self._uow() as uow:
            overrides = {item.seat_id: item for item in uow.seats.list_all()}
        return tuple(
            seat_view(floor.floor_id, room.room_id, seat, overrides.get(seat.seat_id))
            for floor in seed.floors
            for room in floor.rooms
            for seat in room.seats
        )

    def update_seat(self, actor: Actor, seat_id: str, cmd: SeatCommand) -> SeatView:
        ensure_allowed(
            actor.to_subject(),
            Capability.ORG_MANAGE,
            Resource(kind="seat", team_id=cmd.team_id),
        )
        seed = self._seed.load()
        seat = seed.seat_index().get(seat_id)
        if seat is None:
            raise NotFoundError("工位不存在")
        with self._uow() as uow:
            existing = uow.seats.get(seat_id)
            assignment = self._merge(seat_id, existing, cmd)
            uow.seats.upsert(assignment)
            uow.commit()
            location = self._locate(seed, seat_id)
        floor_id, room_id = location
        return seat_view(floor_id, room_id, seat, assignment)

    @staticmethod
    def _merge(
        seat_id: str, existing: SeatAssignment | None, cmd: SeatCommand
    ) -> SeatAssignment:
        return rules.merge_seat(
            seat_id,
            team_id=cmd.team_id if cmd.team_id is not None else _field(existing, "team_id"),
            position_id=(
                cmd.position_id
                if cmd.position_id is not None
                else _field(existing, "position_id")
            ),
            x=cmd.x if cmd.x is not None else _field(existing, "x"),
            y=cmd.y if cmd.y is not None else _field(existing, "y"),
            rotation=cmd.rotation if cmd.rotation is not None else _field(existing, "rotation"),
        )

    @staticmethod
    def _locate(seed: LayoutDef, seat_id: str) -> tuple[str, str]:
        for floor in seed.floors:
            for room in floor.rooms:
                if any(seat.seat_id == seat_id for seat in room.seats):
                    return floor.floor_id, room.room_id
        raise NotFoundError("工位不存在")


def _field(assignment: SeatAssignment | None, name: str):
    return getattr(assignment, name) if assignment is not None else None
