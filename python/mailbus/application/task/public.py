"""任务公开投影：复用 task.updated 大屏事件，只带脱敏进度字段。"""

from __future__ import annotations

from mailbus.application.task.reader import TaskReader
from mailbus.core.shared.errors import NotFoundError

_ACTIVE_STATES = ("running", "dispatched", "blocked", "waiting_human")
_TERMINAL_STATES = ("done", "skipped")


def publish_task_updated(events, seat_of, reader: TaskReader, task_id: str) -> None:
    if events is None:
        return
    try:
        detail = reader.detail(task_id)
    except NotFoundError:
        return
    current = _current_node(detail.nodes)
    done = sum(1 for node in detail.nodes if node.state in _TERMINAL_STATES)
    seat_id = ""
    if seat_of is not None and detail.task.owner_id:
        seat_id = seat_of(detail.task.owner_id)
    events.publish("task.updated", {
        "task_id": task_id,
        "seat_id": seat_id,
        "title": detail.task.title,
        "state": detail.task.state.value,
        "current_node": current.name if current else "",
        "node_state": current.state if current else "",
        "progress_done": done,
        "progress_total": len(detail.nodes),
        "updated_at": detail.task.updated_at.isoformat()
        if detail.task.updated_at else None,
    })


def _current_node(nodes):
    for state in _ACTIVE_STATES:
        for node in nodes:
            if node.state == state:
                return node
    for node in nodes:
        if node.state == "pending":
            return node
    return nodes[-1] if nodes else None
