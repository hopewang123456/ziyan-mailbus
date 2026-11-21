"""Agent 台账的纯函数状态转移。

只负责校验与生成新实例；落库、事务与事件投递由 application 完成。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from mailbus.core.agents.models import Agent
from mailbus.core.agents.values import (
    MAX_FRAMEWORK_LENGTH,
    MAX_NAME_LENGTH,
    PATCHABLE_FIELDS,
)
from mailbus.core.shared.errors import InvalidStateError
from mailbus.core.shared.events import DomainEvent


def _event(kind: str, **payload: object) -> DomainEvent:
    return DomainEvent(kind=kind, payload=dict(payload))


def _text(value: object, label: str, limit: int) -> str:
    if not isinstance(value, str):
        raise InvalidStateError(f"{label}必须是字符串")
    text = value.strip()
    if not text:
        raise InvalidStateError(f"{label}不能为空")
    if len(text) > limit:
        raise InvalidStateError(f"{label}不能超过 {limit} 个字符")
    return text


def _framework(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidStateError("框架必须是字符串")
    text = value.strip()
    if len(text) > MAX_FRAMEWORK_LENGTH:
        raise InvalidStateError(f"框架不能超过 {MAX_FRAMEWORK_LENGTH} 个字符")
    return text


def _optional(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidStateError(f"{label}必须是字符串")
    text = value.strip()
    return text or None


def create_agent(
    agent_id: str,
    *,
    name: str,
    framework: str = "",
    model: str | None = None,
    endpoint: str | None = None,
    enabled: bool = True,
    now: datetime,
) -> tuple[Agent, tuple[DomainEvent, ...]]:
    """登记一个 Agent；名称必填，框架与端点可后补。"""
    agent = Agent(
        agent_id=agent_id,
        name=_text(name, "Agent 名称", MAX_NAME_LENGTH),
        framework=_framework(framework),
        model=_optional(model, "模型"),
        endpoint=_optional(endpoint, "端点"),
        enabled=enabled,
        created_at=now,
        updated_at=now,
    )
    event = _event(
        "agents.agent_created",
        agent_id=agent.agent_id,
        name=agent.name,
        at=now.isoformat(),
    )
    return agent, (event,)


def update_agent(
    agent: Agent, changes: dict[str, object], now: datetime
) -> tuple[Agent, tuple[DomainEvent, ...]]:
    """按字段更新；未提供或值未变化的字段不产生事件。"""
    unknown = set(changes) - PATCHABLE_FIELDS
    if unknown:
        raise InvalidStateError(f"不允许修改字段：{', '.join(sorted(unknown))}")
    values: dict[str, object] = {}
    if "name" in changes:
        values["name"] = _text(changes["name"], "Agent 名称", MAX_NAME_LENGTH)
    if "framework" in changes:
        values["framework"] = _framework(changes["framework"])
    if "model" in changes:
        values["model"] = _optional(changes["model"], "模型")
    if "endpoint" in changes:
        values["endpoint"] = _optional(changes["endpoint"], "端点")
    if "enabled" in changes:
        values["enabled"] = bool(changes["enabled"])
    if all(getattr(agent, key) == value for key, value in values.items()):
        return agent, ()
    updated = replace(agent, updated_at=now, **values)
    event = _event(
        "agents.agent_updated",
        agent_id=agent.agent_id,
        fields=sorted(values),
        at=now.isoformat(),
    )
    return updated, (event,)


def delete_agent(agent: Agent, now: datetime) -> tuple[DomainEvent, ...]:
    """删除台账记录；是否被员工绑定由用例层先行校验。"""
    return (
        _event(
            "agents.agent_deleted",
            agent_id=agent.agent_id,
            name=agent.name,
            at=now.isoformat(),
        ),
    )
