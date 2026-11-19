"""MCP 入口：发送走同一用例；拉取读取本员工的 pull 队列。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import message as mapper
from mailbus.api.schemas.message import MessageIn, MessageOut
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class PullItem(BaseModel):
    event_id: str
    kind: str
    payload: dict
    attempts: int


@router.post("/messages", response_model=MessageOut, status_code=201, summary="MCP 发送")
@declares(Capability.MESSAGE_SEND)
def send_message(payload: MessageIn, request: Request) -> MessageOut:
    service = request.app.state.container.messages
    view = service.send(get_actor(request), mapper.message_command(payload, "mcp"))
    return mapper.to_message_out(view)


@router.get("/pull", response_model=list[PullItem], summary="MCP 拉取")
def pull_events(request: Request) -> list[PullItem]:
    actor = get_actor(request)
    items = request.app.state.container.mcp_pull.drain(actor.employee_id)
    return [PullItem(**item) for item in items]
