"""布局投影的映射（application DTO → wire）。"""

from __future__ import annotations

from mailbus.api.schemas.layout import (
    LayoutFloorOut,
    LayoutRoomOut,
    LayoutSeatOut,
    OfficeSiteOut,
    PublicLayoutFloorOut,
    PublicLayoutRoomOut,
    PublicLayoutSeatOut,
    PublicOfficeSiteOut,
    PublicSeatAgentOut,
    SeatAgentOut,
)
from mailbus.application.org.dto import (
    LayoutFloorView,
    LayoutRoomView,
    LayoutSeatView,
    OfficeSiteView,
    SeatAgentView,
)


def to_office_site_out(view: OfficeSiteView) -> OfficeSiteOut:
    return OfficeSiteOut(
        site_id=view.site_id,
        name=view.name,
        org_name=view.org_name,
        floors=[_floor(floor) for floor in view.floors],
    )


def _floor(view: LayoutFloorView) -> LayoutFloorOut:
    return LayoutFloorOut(
        floor_id=view.floor_id,
        name=view.name,
        level=view.level,
        rooms=[_room(room) for room in view.rooms],
    )


def _room(view: LayoutRoomView) -> LayoutRoomOut:
    return LayoutRoomOut(
        room_id=view.room_id,
        name=view.name,
        kind=view.kind,
        x=view.x,
        y=view.y,
        w=view.w,
        h=view.h,
        seats=[_seat(seat) for seat in view.seats],
    )


def _seat(view: LayoutSeatView) -> LayoutSeatOut:
    return LayoutSeatOut(
        seat_id=view.seat_id,
        x=view.x,
        y=view.y,
        rotation=view.rotation,
        agent=None if view.agent is None else _agent(view.agent),
    )


def _agent(view: SeatAgentView) -> SeatAgentOut:
    return SeatAgentOut(
        agent_id=view.agent_id,
        display_name=view.display_name,
        position=view.position,
        team=view.team,
        status=view.status,
        task=view.task,
        last_heartbeat=view.last_heartbeat,
        bound_agent_id=view.bound_agent_id,
        agent_name=view.agent_name,
        agent_framework=view.agent_framework,
        task_id=view.task_id,
        task_state=view.task_state,
        current_node=view.current_node,
        node_state=view.node_state,
        progress_done=view.progress_done,
        progress_total=view.progress_total,
        pair_id=view.pair_id,
        partner_name=view.partner_name,
    )


def to_public_office_site_out(view: OfficeSiteView) -> PublicOfficeSiteOut:
    return PublicOfficeSiteOut(
        site_id=view.site_id,
        name=view.name,
        org_name=view.org_name,
        floors=[_public_floor(floor) for floor in view.floors],
    )


def _public_floor(view: LayoutFloorView) -> PublicLayoutFloorOut:
    return PublicLayoutFloorOut(
        floor_id=view.floor_id,
        name=view.name,
        level=view.level,
        rooms=[_public_room(room) for room in view.rooms],
    )


def _public_room(view: LayoutRoomView) -> PublicLayoutRoomOut:
    return PublicLayoutRoomOut(
        room_id=view.room_id,
        name=view.name,
        kind=view.kind,
        x=view.x,
        y=view.y,
        w=view.w,
        h=view.h,
        seats=[_public_seat(seat) for seat in view.seats],
    )


def _public_seat(view: LayoutSeatView) -> PublicLayoutSeatOut:
    agent = view.agent
    return PublicLayoutSeatOut(
        seat_id=view.seat_id,
        x=view.x,
        y=view.y,
        rotation=view.rotation,
        agent=None
        if agent is None
        else PublicSeatAgentOut(
            display_name=agent.display_name,
            position=agent.position,
            team=agent.team,
            status=agent.status,
            task=agent.task,
            agent_name=agent.agent_name,
            agent_framework=agent.agent_framework,
            task_state=agent.task_state,
            current_node=agent.current_node,
            node_state=agent.node_state,
            progress_done=agent.progress_done,
            progress_total=agent.progress_total,
            pair_id=agent.pair_id,
            partner_name=agent.partner_name,
        ),
    )
