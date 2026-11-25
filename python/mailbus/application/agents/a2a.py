"""A2A 单入口：token 认证、心跳、结果幂等与消息转发。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace

from mailbus.application.identity.dto import Actor
from mailbus.application.messaging.dto import SendMessageCommand
from mailbus.application.task.dto import SubmitResultCommand
from mailbus.core.agents import rules
from mailbus.core.agents.models import Agent
from mailbus.core.agents.ports import AgentsUnitOfWork, TokenCipherPort
from mailbus.core.identity.values import EmployeeStatus
from mailbus.core.shared.errors import (
    AuthenticationError,
    PermissionDeniedError,
    StaleRunError,
    UnprocessableError,
)
from mailbus.core.shared.ports import Clock, IdGenerator
from mailbus.core.shared.values import Capability
from mailbus.core.workflow.models import RunState, TaskArtifact

_FAILED_STATUSES = frozenset({"failed", "rejected", "needs_human", "needs_info"})


class A2AService:
    def __init__(
        self,
        uow_factory: Callable[[], AgentsUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        cipher: TokenCipherPort,
        tasks,
        messaging,
        guard: Callable[[str], str],
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._ids = ids
        self._cipher = cipher
        self._tasks = tasks
        self._messaging = messaging
        self._guard = guard

    # ---- 认证 ----

    def authenticate(self, token: str | None) -> Agent:
        if not token:
            raise AuthenticationError("缺少 Agent token")
        digest = self._cipher.lookup_digest(token)
        with self._uow() as uow:
            agent = uow.agents.find_by_token_lookup(digest)
        if agent is None or not agent.enabled or agent.deleted_at is not None:
            raise AuthenticationError("Agent token 无效")
        return agent

    # ---- 入口 ----

    def handle(self, agent: Agent, msg) -> dict[str, object]:
        if msg.type == "heartbeat":
            return self._heartbeat(agent, msg)
        if msg.type == "result":
            return self._result(agent, msg)
        if msg.type == "message":
            return self._message(agent, msg)
        return {"message_id": msg.message_id or self._ids.new("ack"), "accepted": True}

    # ---- 心跳 ----

    def _heartbeat(self, agent: Agent, msg) -> dict[str, object]:
        now = self._clock.now()
        endpoint = self._guard_endpoint(msg.endpoint)
        updated = rules.heartbeat(agent, endpoint, now)
        with self._uow() as uow:
            uow.agents.save(updated)
            for employee in uow.employees.list_all():
                if employee.agent_id == agent.agent_id:
                    status = (
                        EmployeeStatus.OFFLINE
                        if employee.status is EmployeeStatus.DEREGISTERED
                        else EmployeeStatus.ACTIVE
                    )
                    uow.employees.save(
                        replace(employee, status=status, last_heartbeat=now)
                    )
            uow.commit()
        return {
            "message_id": msg.message_id or self._ids.new("ack"),
            "accepted": True,
            "endpoint_review_status": updated.endpoint_review_status,
        }

    # ---- 结果 ----

    def _result(self, agent: Agent, msg) -> dict[str, object]:
        if not msg.run_id:
            raise UnprocessableError("result 必须携带 run_id")
        if msg.attempt_no is None:
            raise UnprocessableError("result 必须携带 attempt_no")
        result = _compose_result(msg)
        now = self._clock.now()
        with self._uow() as uow:
            run = uow.runs.get(msg.run_id)
            if run is None:
                self._audit(uow, agent, msg, "run 不存在")
                raise StaleRunError("执行实例不存在")
            employee = uow.employees.get(run.assigned_employee_id or "")
            if employee is None or employee.agent_id != agent.agent_id:
                raise PermissionDeniedError("该执行实例不属于当前 Agent")
            if run.attempt_no != msg.attempt_no:
                self._audit(uow, agent, msg, "attempt_no 已过期")
                raise StaleRunError("执行实例 attempt 已过期")
            if run.state in (RunState.DONE, RunState.FAILED):
                if run.result == result:
                    return _ack(msg, self._ids, duplicate=True)
                self._audit(uow, agent, msg, "终态结果不一致")
                raise StaleRunError("该执行实例已提交过其他结果")
            artifact_ids = self._record_artifacts(uow, run, msg, agent, now)
            actor = Actor.of(employee)
            task_id, node_id = run.task_id, run.node_id
            uow.commit()
        self._tasks.submit(
            actor,
            task_id,
            node_id,
            SubmitResultCommand(
                attempt_no=msg.attempt_no, result=result, artifact_ids=artifact_ids
            ),
        )
        return _ack(msg, self._ids)

    # ---- 消息 ----

    def _message(self, agent: Agent, msg) -> dict[str, object]:
        with self._uow() as uow:
            employees = [
                item for item in uow.employees.list_all()
                if item.agent_id == agent.agent_id
            ]
        if not employees:
            raise PermissionDeniedError("Agent 未绑定员工，无法发送消息")
        actor = Actor.of(employees[0])
        if Capability.MESSAGE_SEND not in actor.capabilities:
            raise PermissionDeniedError("缺少 message_send")
        message = self._messaging.send(
            replace(actor, endpoint_approved=True),
            SendMessageCommand(
                recipient_id=msg.payload.get("recipient_id"),
                body=msg.body or msg.output or "",
            ),
        )
        return {
            "message_id": message.message_id,
            "accepted": True,
            "duplicate": False,
        }

    # ---- 辅助 ----

    def _record_artifacts(self, uow, run, msg, agent: Agent, now) -> tuple[str, ...]:
        ids: list[str] = []
        for item in msg.artifacts:
            if item.type == "artifact" and item.artifact_id:
                ids.append(item.artifact_id)
                continue
            if item.type != "path" or not item.file_path:
                continue
            artifact_id = self._ids.new("art")
            uow.artifacts.add(
                TaskArtifact(
                    artifact_id=artifact_id,
                    task_id=run.task_id,
                    node_id=run.node_id,
                    run_id=run.run_id,
                    file_path=item.file_path,
                    file_name=item.file_name or item.file_path.rsplit("/", 1)[-1],
                    created_by=run.assigned_employee_id or agent.agent_id,
                    created_at=now,
                    artifact_type="file",
                    description=item.description,
                )
            )
            ids.append(artifact_id)
        return tuple(ids)

    @staticmethod
    def _audit(uow, agent: Agent, msg, reason: str) -> None:
        uow.audit.record(
            agent.agent_id,
            "a2a.result_rejected",
            msg.run_id,
            {"reason": reason, "attempt_no": msg.attempt_no},
        )
        uow.commit()

    def _guard_endpoint(self, endpoint: str | None) -> str | None:
        return self._guard(endpoint) if endpoint else None


def _compose_result(msg) -> str:
    payload = dict(msg.payload or {})
    status = msg.status or "completed"
    if msg.output is not None:
        payload.setdefault("output", msg.output)
    if status in _FAILED_STATUSES:
        payload["status"] = status
        return json.dumps(payload, ensure_ascii=False)
    if payload:
        payload.setdefault("status", "completed")
        return json.dumps(payload, ensure_ascii=False)
    return msg.output or json.dumps({"status": "completed"}, ensure_ascii=False)


def _ack(msg, ids, *, duplicate: bool = False) -> dict[str, object]:
    return {
        "message_id": msg.message_id or ids.new("ack"),
        "accepted": True,
        "duplicate": duplicate,
    }
