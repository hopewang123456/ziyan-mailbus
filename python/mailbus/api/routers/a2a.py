"""A2A 单入口：Agent token 认证后分发 heartbeat/result/message/ack。"""

from __future__ import annotations

from fastapi import APIRouter, Header, Request

from mailbus.api.deps import PUBLIC, declares
from mailbus.api.schemas.contract.agent import A2aAckOut, A2aMessageIn

router = APIRouter(prefix="/api/a2a", tags=["a2a"])


@router.post("/messages", response_model=A2aAckOut, status_code=201, summary="A2A 单入口")
@declares(PUBLIC)
def push_message(
    payload: A2aMessageIn,
    request: Request,
    authorization: str | None = Header(default=None),
) -> A2aAckOut:
    token = _bearer(authorization)
    service = request.app.state.container.a2a_messages
    agent = service.authenticate(token)
    result = service.handle(agent, payload)
    return A2aAckOut(
        message_id=str(result["message_id"]),
        accepted=bool(result.get("accepted", True)),
        duplicate=bool(result.get("duplicate", False)),
    )


def _bearer(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()
