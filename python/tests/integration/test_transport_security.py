"""传输层安全回归：H4 路径穿越净化、H5 A2A 协议与端点审核。"""

from __future__ import annotations

from contextlib import closing

from mailbus.adapters.persistence.sqlite.connection import connect
from mailbus.adapters.persistence.sqlite.migrations import apply_migrations
from mailbus.adapters.transport.a2a import A2aTransport
from mailbus.adapters.transport.file_bus import FileBusTransport
from mailbus.adapters.transport.mcp_pull import McpPullTransport
from mailbus.application.agents.dto import (
    AgentInviteCommand,
    AgentRegisterCommand,
    AgentUpdateCommand,
)
from mailbus.application.identity.dto import Actor
from mailbus.application.org.dto import PositionCommand
from mailbus.bootstrap.container import Container
from mailbus.bootstrap.settings import Settings
from mailbus.core.identity.values import AccountType, EmployeeStatus
from mailbus.core.shared.events import OutboxEvent
from mailbus.core.shared.values import Capability, DataScope


def _event(recipient_id: str) -> OutboxEvent:
    return OutboxEvent(
        event_id="evt-1",
        kind="message.sent",
        payload={"recipient_id": recipient_id, "channel": "file_bus"},
    )


def test_recipient_traversal_is_sanitized(tmp_path):
    base = tmp_path / "fb"
    FileBusTransport(base).send(_event("../../escaped"))

    # 绝不能写出 base 目录之外
    assert not (tmp_path / "escaped").exists()
    assert not (tmp_path.parent / "escaped").exists()

    files = list((base / "outbox").rglob("evt-1.json"))
    assert len(files) == 1
    rel = files[0].relative_to(base / "outbox")
    assert len(rel.parts) == 2  # <净化目录>/evt-1.json
    assert "/" not in rel.parts[0] and "\\" not in rel.parts[0]


def test_mcp_pull_recipient_traversal_is_sanitized(tmp_path):
    base = tmp_path / "mcp"
    McpPullTransport(base).send(_event("../../escape_mcp"))
    assert not (tmp_path.parent / "escape_mcp").exists()
    items = McpPullTransport(base).drain("../../escape_mcp")
    assert [item["event_id"] for item in items] == ["evt-1"]


def test_a2a_rejects_non_http_scheme():
    transport = A2aTransport(lambda _: "file:///etc/passwd")
    result = transport.send(_event("emp-x"))
    assert result.ok is False
    assert result.error_code == "a2a_invalid_endpoint"


def test_a2a_requires_endpoint():
    transport = A2aTransport(lambda _: None)
    result = transport.send(_event("emp-x"))
    assert result.ok is False
    assert result.error_code == "endpoint_missing"


def _all_actor() -> Actor:
    return Actor(
        employee_id="emp_admin",
        account_type=AccountType.HUMAN,
        status=EmployeeStatus.ACTIVE,
        capabilities=frozenset({Capability.ALL}),
        data_scope=DataScope.GLOBAL,
    )


def test_container_endpoint_gated_on_approval(tmp_path):
    container = Container(Settings(data_dir=tmp_path))
    with closing(connect(container.settings.db_path)) as conn:
        apply_migrations(conn)

    actor = _all_actor()
    position_command = PositionCommand(name="执行岗")
    position = container.org_admin.structure.create_position(
        actor, position_command.name, list(position_command.capabilities)
    )
    invite = container.agent_registration.create_invite(
        actor,
        AgentInviteCommand(employee_name="机器人", position_id=position.position_id),
    )
    registration = container.agent_registration.register(
        AgentRegisterCommand(
            invite_code=invite.invite_code,
            name="机器人",
            endpoint="https://agent.example/hook",
        )
    )
    emp_id = registration.employee_id
    agent_id = registration.agent_id

    # 注册后端点待审批：不解析
    assert container._endpoint_of(emp_id) is None

    # 审核通过后才解析
    container.agents.approve_endpoint(actor, agent_id)
    assert container._endpoint_of(emp_id) == "https://agent.example/hook"

    # 禁用 Agent：立即失效
    container.agents.update(
        actor, agent_id, AgentUpdateCommand(changes={"enabled": False})
    )
    assert container._endpoint_of(emp_id) is None
