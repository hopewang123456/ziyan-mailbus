"""孪生布局只读查询：种子几何 + 工位覆盖 + 员工投影。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from mailbus.application.identity.dto import OccupantView
from mailbus.application.identity.staff import StaffService
from mailbus.application.org.dto import (
    LayoutFloorView,
    LayoutRoomView,
    LayoutSeatView,
    OfficeSiteView,
    SeatAgentView,
)
from mailbus.application.workflow.dto import TaskView
from mailbus.application.workflow.tasks import TaskService
from mailbus.core.agents.models import AgentSummary
from mailbus.core.agents.ports import AgentDirectoryPort
from mailbus.core.identity.values import EmployeeStatus
from mailbus.core.org.models import LayoutDef, SeatAssignment
from mailbus.core.org.ports import LayoutSeedPort, OrgUnitOfWork
from mailbus.core.workflow.values import TaskState

_STATUS_BY_EMPLOYEE = {
    EmployeeStatus.ACTIVE: "online",
    EmployeeStatus.OFFLINE: "offline",
}

# 「手上有业务」：已派发（queued）/执行中/阻塞 的任务都算忙。
_BUSY_TASK_STATES = frozenset(
    {TaskState.QUEUED.value, TaskState.RUNNING.value, TaskState.BLOCKED.value}
)

_DONE_NODE_STATES = frozenset({"done", "skipped"})
_ACTIVE_NODE_STATES = ("running", "dispatched", "blocked")


class LayoutQuery:
    def __init__(
        self,
        uow_factory: Callable[[], OrgUnitOfWork],
        seed: LayoutSeedPort,
        staff: StaffService,
        tasks: TaskService,
        agents: AgentDirectoryPort,
    ) -> None:
        self._uow = uow_factory
        self._seed = seed
        self._staff = staff
        self._tasks = tasks
        self._agents = agents

    def get(self) -> OfficeSiteView:
        seed = self._seed.load()
        with self._uow() as uow:
            overrides = {item.seat_id: item for item in uow.seats.list_all()}
            team_names = {team.team_id: team.name for team in uow.teams.list_all()}
            position_names = {
                position.position_id: position.name for position in uow.positions.list_all()
            }
        occupants = {
            occupant.seat_id: occupant
            for occupant in self._staff.occupants()
            if occupant.seat_id
        }
        summaries = self._agents.summaries(
            tuple(occupant.agent_id for occupant in occupants.values() if occupant.agent_id)
        )
        busy = self._busy_tasks()
        floors = tuple(
            _floor_view(
                floor,
                overrides,
                occupants,
                team_names,
                position_names,
                busy,
                summaries,
            )
            for floor in seed.floors
        )
        return OfficeSiteView(
            site_id=seed.site_id,
            name=seed.name,
            org_name=seed.org_name,
            floors=floors,
        )

    def _busy_tasks(self) -> dict[str, TaskView]:
        busy: dict[str, TaskView] = {}
        for task in self._tasks.list_tasks():
            if task.owner_id and task.state in _BUSY_TASK_STATES:
                busy.setdefault(task.owner_id, task)
        return busy


def _floor_view(
    floor,
    overrides: dict[str, SeatAssignment],
    occupants: dict[str, OccupantView],
    team_names: dict[str, str],
    position_names: dict[str, str],
    busy: dict[str, TaskView],
    summaries: dict[str, AgentSummary],
) -> LayoutFloorView:
    return LayoutFloorView(
        floor_id=floor.floor_id,
        name=floor.name,
        level=floor.level,
        rooms=tuple(
            _room_view(
                floor.floor_id,
                room,
                overrides,
                occupants,
                team_names,
                position_names,
                busy,
                summaries,
            )
            for room in floor.rooms
        ),
    )


def _room_view(
    floor_id: str,
    room,
    overrides: dict[str, SeatAssignment],
    occupants: dict[str, OccupantView],
    team_names: dict[str, str],
    position_names: dict[str, str],
    busy: dict[str, TaskView],
    summaries: dict[str, AgentSummary],
) -> LayoutRoomView:
    seats = []
    for seat in room.seats:
        assignment = overrides.get(seat.seat_id)
        occupant = occupants.get(seat.seat_id)
        seats.append(
            LayoutSeatView(
                seat_id=seat.seat_id,
                x=assignment.x if assignment and assignment.x is not None else seat.x,
                y=assignment.y if assignment and assignment.y is not None else seat.y,
                rotation=(
                    assignment.rotation
                    if assignment and assignment.rotation is not None
                    else seat.rotation
                ),
                agent=(
                    _agent_view(
                        occupant,
                        team_names,
                        position_names,
                        busy.get(occupant.employee_id),
                        summaries.get(occupant.agent_id or ""),
                        assignment.team_id if assignment else None,
                        assignment.position_id if assignment else None,
                    )
                    if occupant is not None
                    else None
                ),
            )
        )
    return LayoutRoomView(
        room_id=room.room_id,
        name=room.name,
        kind=room.kind.value,
        x=room.x,
        y=room.y,
        w=room.w,
        h=room.h,
        seats=tuple(seats),
    )


def _agent_view(
    occupant: OccupantView,
    team_names: dict[str, str],
    position_names: dict[str, str],
    task: TaskView | None,
    summary: AgentSummary | None,
    seat_team_id: str | None,
    seat_position_id: str | None,
) -> SeatAgentView:
    status = _status_of(occupant.status)
    if status != "offline" and task is not None:
        status = "busy"
    task_id, task_state, current_node, node_state, done, total = _execution(task)
    return SeatAgentView(
        agent_id=occupant.employee_id,
        display_name=occupant.display_name,
        position=position_names.get(
            occupant.position_id or seat_position_id or "", ""
        ),
        team=team_names.get(occupant.team_id or seat_team_id or "", ""),
        status=status,
        task=task.title if task else "",
        last_heartbeat=_heartbeat(occupant.last_heartbeat),
        bound_agent_id=occupant.agent_id or "",
        agent_name=summary.name if summary else "",
        agent_framework=summary.framework if summary else "",
        task_id=task_id,
        task_state=task_state,
        current_node=current_node,
        node_state=node_state,
        progress_done=done,
        progress_total=total,
    )


def _execution(task: TaskView | None) -> tuple[str, str, str, str, int, int]:
    """节点级执行态投影；自由任务没有节点，进度为 0/0。"""
    if task is None:
        return "", "", "", "", 0, 0
    current = _current_node(task)
    done = sum(1 for node in task.nodes if node.state in _DONE_NODE_STATES)
    return (
        task.task_id,
        task.state,
        current.name if current else "",
        current.state if current else "",
        done,
        len(task.nodes),
    )


def _current_node(task: TaskView):
    for state in _ACTIVE_NODE_STATES:
        for node in task.nodes:
            if node.state == state:
                return node
    for node in task.nodes:
        if node.state == "pending":
            return node
    return task.nodes[-1] if task.nodes else None


def _status_of(status: str) -> str:
    try:
        return _STATUS_BY_EMPLOYEE.get(EmployeeStatus(status), "offline")
    except ValueError:
        return "offline"


def _heartbeat(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""
