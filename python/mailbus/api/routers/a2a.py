"""A2A 入口：外部 agent 直推消息，权限判定仍在发送用例内。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from mailbus.api.deps import declares, get_actor
from mailbus.api.mappers import message as mapper
from mailbus.api.schemas.message import MessageIn, MessageOut
from mailbus.core.shared.values import Capability

router = APIRouter(prefix="/api/a2a", tags=["a2a"])


@router.post("/messages", response_model=MessageOut, status_code=201, summary="A2A 直推")
@declares(Capability.MESSAGE_SEND)
def push_message(payload: MessageIn, request: Request) -> MessageOut:
    service = request.app.state.container.messages
    view = service.send(get_actor(request), mapper.message_command(payload, "a2a"))
    return mapper.to_message_out(view)
