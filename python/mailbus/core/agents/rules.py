"""Agent 台账的纯函数状态转移。

只负责校验与生成新实例；落库、事务与事件投递由 application 完成。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

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


ROTATION_GRACE = timedelta(hours=24)
# 设计约定：连续 90 秒无心跳判离线（见 docs/design/agent-onboarding-template.md）。
HEARTBEAT_TIMEOUT = timedelta(seconds=90)
_heartbeat_timeout = HEARTBEAT_TIMEOUT


def heartbeat_timeout() -> timedelta:
    """当前生效的心跳超时；装配层可按配置注入，默认对齐设计 90s。"""
    return _heartbeat_timeout


def configure_heartbeat_timeout(seconds: float) -> None:
    """装配期一次性注入心跳超时（非正值回落默认），避免配置项形同虚设。"""
    global _heartbeat_timeout
    value = float(seconds)
    _heartbeat_timeout = (
        timedelta(seconds=value) if value > 0 else HEARTBEAT_TIMEOUT
    )


def is_online(agent: Agent, now: datetime) -> bool:
    """运行态在线判定只依赖心跳；注册记录本身永不因离线删除。"""
    if agent.deleted_at is not None or not agent.enabled:
        return False
    if agent.last_seen_at is None:
        return False
    return now - agent.last_seen_at <= _heartbeat_timeout


def dispatchable(agent: Agent, now: datetime) -> bool:
    """待审批、被拒绝、离线、停用均不得派单。"""
    return (
        agent.endpoint_review_status == "approved"
        and bool(agent.endpoint)
        and is_online(agent, now)
    )


def rotate_token(
    agent: Agent,
    *,
    ciphertext: str,
    lookup_hash: str,
    now: datetime,
) -> tuple[Agent, tuple[DomainEvent, ...]]:
    """轮转 token：旧 token 保留 24h 宽限，随后应被吊销清理。"""
    updated = replace(
        agent,
        endpoint_token_prev=agent.endpoint_token,
        endpoint_token_prev_lookup_hash=agent.endpoint_token_lookup_hash,
        endpoint_token_prev_expires_at=now + ROTATION_GRACE if agent.endpoint_token else None,
        endpoint_token=ciphertext,
        endpoint_token_lookup_hash=lookup_hash,
        updated_at=now,
    )
    return updated, (_event("agents.token_rotated", agent_id=agent.agent_id,
                            at=now.isoformat()),)


def revoke_token(agent: Agent, now: datetime) -> tuple[Agent, tuple[DomainEvent, ...]]:
    """吊销后当前与宽限 token 同时失效，入站立即 401。"""
    updated = replace(
        agent,
        endpoint_token=None,
        endpoint_token_lookup_hash=None,
        endpoint_token_prev=None,
        endpoint_token_prev_lookup_hash=None,
        endpoint_token_prev_expires_at=None,
        last_seen_at=None,
        updated_at=now,
    )
    return updated, (_event("agents.token_revoked", agent_id=agent.agent_id,
                            at=now.isoformat()),)


def heartbeat(agent: Agent, endpoint: str | None, now: datetime) -> Agent:
    """心跳只更新在线态；新上报地址一律进入待审批，不覆盖已批准终点。"""
    changes: dict[str, object] = {"last_seen_at": now, "updated_at": now}
    if endpoint and endpoint != agent.endpoint and endpoint != agent.pending_endpoint:
        changes["pending_endpoint"] = endpoint
        changes["endpoint_review_status"] = "pending"
    return replace(agent, **changes)


def approve_endpoint(agent: Agent, reviewer: str, now: datetime) -> Agent:
    if not agent.pending_endpoint:
        raise InvalidStateError("没有待审批的 endpoint")
    return replace(
        agent,
        endpoint=agent.pending_endpoint,
        pending_endpoint=None,
        endpoint_review_status="approved",
        endpoint_approved_by=reviewer,
        endpoint_approved_at=now,
        updated_at=now,
    )


def reject_endpoint(agent: Agent, reviewer: str, now: datetime) -> Agent:
    if not agent.pending_endpoint:
        raise InvalidStateError("没有待审批的 endpoint")
    return replace(
        agent,
        pending_endpoint=None,
        endpoint_review_status="rejected",
        endpoint_approved_by=reviewer,
        endpoint_approved_at=now,
        updated_at=now,
    )
