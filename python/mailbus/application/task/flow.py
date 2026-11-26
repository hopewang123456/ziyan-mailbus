"""任务推进：派发、汇聚、重试、循环保护与升级。

唯一推进入口；调用方（TaskEngine）负责权限与事务边界。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

from mailbus.application.events import enqueue_events
from mailbus.application.task.conditions import evaluate, parse_result
from mailbus.application.task.fanout import FanoutMixin
from mailbus.core.approval import rules as approval_rules
from mailbus.core.approval.values import ApprovalStatus, ApprovalTier
from mailbus.core.identity.values import AccountType
from mailbus.core.shared.events import DomainEvent
from mailbus.core.task import GraphIndex
from mailbus.core.workflow.models import Task, TaskEscalation, TaskNode, TaskRun
from mailbus.core.workflow.values import (
    DEFAULT_APPROVAL_TIMEOUT_MINUTES,
    DEFAULT_WORK_TIMEOUT_SECONDS,
    NodeState,
    OPEN_RUN_STATES,
    RunState,
    TaskState,
    TerminationReason,
    EscalationReason,
)

FREE_NODE_ID = "free"
TERMINAL_NODE_STATES = frozenset({NodeState.DONE, NodeState.FAILED, NodeState.SKIPPED})


def graph_of(uow, task: Task) -> GraphIndex | None:
    if not task.workflow_id or task.workflow_version is None:
        return None
    nodes, edges = uow.graphs.load(task.workflow_id, task.workflow_version)
    return GraphIndex(nodes, edges)


class Flow(FanoutMixin):
    def __init__(self, uow, task: Task, graph: GraphIndex | None, ids, clock) -> None:
        self.uow = uow
        self.task = task
        self.graph = graph
        self.ids = ids
        self.clock = clock
        self.nodes = {node.node_id: node for node in uow.tasks.nodes(task.task_id)}
        self.blocked = task.state is TaskState.BLOCKED
        self.approval_ids: list[str] = []
        self.last_attempt = 0

    # ---- 入口 ----

    def start_graph(self) -> None:
        assert self.graph is not None
        starts = [node_id for node_id in self.graph.start_nodes()
                  if self._wf(node_id) and self._wf(node_id).node_type == "start"]
        for node_id in starts or self.graph.start_nodes():
            self.dispatch(node_id)
        self.settle()

    def start_free(self, owner_id: str) -> TaskRun:
        now = self.clock.now()
        node = TaskNode(self.task.task_id, FREE_NODE_ID, self.task.title, 0,
                        NodeState.RUNNING, None, now)
        self._save_node(node)
        run = TaskRun(
            run_id=self.ids.new("run"), task_id=self.task.task_id,
            node_id=FREE_NODE_ID, attempt_no=1, state=RunState.DISPATCHED,
            assigned_employee_id=owner_id, dispatched_at=now,
            deadline_at=now + timedelta(seconds=DEFAULT_WORK_TIMEOUT_SECONDS),
        )
        self.uow.runs.add(run)
        self._save_node(replace(node, current_run_id=run.run_id))
        owner = self.uow.employees.get(owner_id)
        if owner is not None and owner.account_type is AccountType.AGENT:
            enqueue_events(self.uow.outbox, [DomainEvent(
                kind="task.assigned",
                payload={
                    "task_id": self.task.task_id,
                    "node_id": FREE_NODE_ID,
                    "node_name": self.task.title,
                    "run_id": run.run_id,
                    "attempt_no": run.attempt_no,
                    "fanout_slot": 0,
                    "title": self.task.title,
                    "recipient_id": owner_id,
                    "channel": "a2a",
                    "at": now.isoformat(),
                },
            )], self.ids, now)
        return run

    # ---- 派发 ----

    def dispatch(self, node_id: str, slot: int = 0, parent: str | None = None) -> None:
        node = self.nodes.get(node_id)
        wf = self._wf(node_id)
        if node is None or wf is None:
            return
        if node.state is NodeState.RUNNING and node.current_run_id:
            return
        if node.state is NodeState.DONE and self._forced(node_id):
            return
        if node.state is NodeState.DONE and self._enter_loop(node, wf):
            return
        if wf.node_type in ("start", "condition"):
            self._save_node(replace(node, state=NodeState.DONE, current_run_id=None))
            self.advance(node_id)
            return
        if wf.node_type == "parallel_join":
            self._join(node_id)
            return
        if wf.node_type == "final_approval":
            self._human(node, wf, approval=True)
            return
        if wf.node_type == "human":
            self._human(node, wf, approval=False)
            return
        self._dispatch_agent(node, wf, parent=parent)

    def _human(self, node: TaskNode, wf, approval: bool) -> None:
        now = self.clock.now()
        attempt = self.uow.runs.max_attempt(self.task.task_id, node.node_id) + 1
        fanout = max(1, int(wf.config.get("fanout") or 1)) if not approval else 1
        group = (f"{self.task.task_id}:{node.node_id}:{attempt}"
                 if fanout > 1 else None)
        slots = range(1, fanout + 1) if fanout > 1 else [0]
        latest = None
        for slot in slots:
            run = TaskRun(
                run_id=self.ids.new("run"), task_id=self.task.task_id,
                node_id=node.node_id, attempt_no=attempt, fanout_slot=slot,
                fanout_group=group, state=RunState.WAITING_HUMAN, dispatched_at=now,
                deadline_at=now + timedelta(seconds=self._timeout(wf)),
            )
            self.uow.runs.add(run)
            latest = run
        self._save_node(replace(node, state=NodeState.RUNNING,
                                current_run_id=latest.run_id if latest else None))
        self._mark_running()
        if approval:
            item, _ = approval_rules.request(
                self.ids.new("appr"), task_id=self.task.task_id, title=node.name,
                tier=ApprovalTier.BLOCKING, requester_id=self.task.created_by,
                node_id=node.node_id, note=None, now=now,
                timeout_minutes=DEFAULT_APPROVAL_TIMEOUT_MINUTES,
            )
            self.uow.approvals.add(item)
            self.approval_ids.append(item.approval_id)

    # ---- 结果与失败 ----

    def complete(self, run: TaskRun, result: str) -> None:
        now = self.clock.now()
        self.uow.runs.save(replace(run, state=RunState.DONE, result=result, completed_at=now))
        node = self.nodes[run.node_id]
        if self._fanout(run.node_id) > 1:
            if self._slots_settled(run.node_id):
                self._save_node(replace(node, state=self._fanout_state(run.node_id)))
                self.advance(run.node_id)
            else:
                self._save_node(replace(node, state=NodeState.RUNNING))
            self.settle()
            return
        self.uow.artifacts.delete_for_node_except(self.task.task_id, run.node_id, run.run_id)
        self._save_node(replace(node, state=NodeState.DONE, current_run_id=run.run_id))
        self.advance(run.node_id)
        self.settle()

    def fail(self, run: TaskRun, result: str | None) -> None:
        now = self.clock.now()
        self.uow.runs.save(replace(run, state=RunState.FAILED, result=result, completed_at=now))
        wf = self._wf(run.node_id)
        attempts = len([item for item in self.uow.runs.list_by_node(
            self.task.task_id, run.node_id) if item.fanout_slot == run.fanout_slot])
        if wf is not None and attempts <= wf.max_retries:
            if self._fanout(run.node_id) > 1:
                self._retry_slot(run, wf)
            else:
                self._save_node(replace(self.nodes[run.node_id],
                                        state=NodeState.PENDING, current_run_id=None))
                self.dispatch(run.node_id)
            return
        self.escalate(EscalationReason.RUN_FAILED, node_id=run.node_id, run_id=run.run_id)
        if self._fanout(run.node_id) > 1:
            # 缺失分片不自动推进：等人工 rerun-join 决策范围
            self._save_node(replace(self.nodes[run.node_id], state=NodeState.FAILED))
            self.settle()
            return
        self._block_with_human(run.node_id, wf)

    # ---- 汇聚与收尾 ----
    def settle(self) -> None:
        if self.task.state in (TaskState.DONE, TaskState.CANCELLED, TaskState.FAILED):
            return
        if self.blocked:
            return
        runs = self.uow.runs.list_by_task(self.task.task_id)
        if any(item.state in OPEN_RUN_STATES for item in runs):
            self._mark_running()
            return
        if all(node.state in TERMINAL_NODE_STATES for node in self.nodes.values()):
            self._save_task(replace(self.task, state=TaskState.DONE))
        elif not self.blocked:
            self._mark_running()

    def advance(self, node_id: str) -> None:
        if self.graph is None:
            return
        edges = self.graph.forward_edges(node_id)
        if not edges:
            return
        targets = self._select(edges, node_id)
        if targets is None:
            self.terminate(TerminationReason.NO_MATCHING_BRANCH)
            return
        for target in targets:
            self.dispatch(target)

    def _select(self, edges, node_id: str) -> list[str] | None:
        if len(edges) == 1:
            if not edges[0].condition:
                return [edges[0].to_node_id]
            return [edges[0].to_node_id] if evaluate(
                edges[0].condition, self._context(node_id)) else None
        context = self._context(node_id)
        conditioned = [edge for edge in edges if edge.condition]
        if conditioned:
            for edge in conditioned:
                if evaluate(edge.condition, context):
                    return [edge.to_node_id]
            return None
        return [edge.to_node_id for edge in edges]

    def terminate(self, reason: TerminationReason) -> None:
        now = self.clock.now()
        for run in self.uow.runs.list_by_task(self.task.task_id):
            if run.state in OPEN_RUN_STATES:
                self.uow.runs.save(replace(run, state=RunState.SKIPPED, completed_at=now))
        for node in self.nodes.values():
            if node.state not in TERMINAL_NODE_STATES:
                self._save_node(replace(node, state=NodeState.SKIPPED))
        self._withdraw_approvals()
        self._save_task(replace(self.task, state=TaskState.CANCELLED,
                                termination_reason=reason.value))

    # ---- 升级与阻塞 ----

    def escalate(self, reason: EscalationReason, node_id: str | None = None,
                 run_id: str | None = None, approval_id: str | None = None,
                 level: int = 1) -> None:
        if self.uow.escalations.has_open(self.task.task_id, reason.value):
            return
        target = "super_admin"
        owner = self.uow.employees.get(self.task.owner_id) if self.task.owner_id else None
        team = self.uow.teams.get(owner.team_id) if owner and owner.team_id else None
        if team is not None and team.leader_employee_id:
            target = team.leader_employee_id
        self.uow.escalations.add(TaskEscalation(
            escalation_id=self.ids.new("esc"), task_id=self.task.task_id,
            reason=reason.value, escalated_to=target, escalated_at=self.clock.now(),
            run_id=run_id, approval_id=approval_id, level=level,
        ))

    def _block_with_human(self, node_id: str, wf) -> None:
        node = self.nodes[node_id]
        now = self.clock.now()
        run = TaskRun(
            run_id=self.ids.new("run"), task_id=self.task.task_id, node_id=node_id,
            attempt_no=self.uow.runs.max_attempt(self.task.task_id, node_id) + 1,
            state=RunState.WAITING_HUMAN, dispatched_at=now,
            deadline_at=now + timedelta(seconds=self._timeout(wf) if wf else 0),
            result=json.dumps({"escalated": True}, ensure_ascii=False),
        )
        self.uow.runs.add(run)
        self._save_node(replace(node, state=NodeState.BLOCKED, current_run_id=run.run_id))
        self.blocked = True
        self._save_task(replace(self.task, state=TaskState.BLOCKED))

    def _forced(self, node_id: str) -> bool:
        """人工 rerun-join 已推进该节点：后续前驱完成不再重复进入循环。"""
        runs = self.uow.runs.list_by_node(self.task.task_id, node_id)
        latest = max((item.attempt_no for item in runs), default=0)
        for item in runs:
            if item.attempt_no != latest or not item.result:
                continue
            try:
                payload = json.loads(item.result)
            except ValueError:
                continue
            if isinstance(payload, dict) and payload.get("forced") is True:
                return True
        return False

    def _enter_loop(self, node: TaskNode, wf) -> bool:
        count = self.task.loop_counters.get(node.node_id, 0) + 1
        counters = {**self.task.loop_counters, node.node_id: count}
        self._save_task(replace(self.task, loop_counters=counters))
        if count <= wf.max_loops:
            self._save_node(replace(node, state=NodeState.PENDING, current_run_id=None))
            return False
        self.escalate(EscalationReason.LOOP_EXCEEDED, node_id=node.node_id)
        self._block_with_human(node.node_id, wf)
        return True

    def reject(self, node_id: str) -> None:
        edges = self.graph.back_edges(node_id) if self.graph else []
        if not edges:
            self.terminate(TerminationReason.APPROVAL_REJECTED)
            return
        node = self.nodes[node_id]
        self._save_node(replace(node, state=NodeState.PENDING, current_run_id=None))
        self.dispatch(edges[0].to_node_id)
        self.settle()

    def approve(self, node_id: str) -> None:
        node = self.nodes[node_id]
        self._save_node(replace(node, state=NodeState.DONE))
        self.advance(node_id)
        self.settle()

    # ---- 小工具 ----

    def _wf(self, node_id: str):
        return self.graph.node(node_id) if self.graph else None

    def _fanout(self, node_id: str) -> int:
        wf = self._wf(node_id)
        return int(wf.config.get("fanout") or 1) if wf else 1

    def _timeout(self, wf) -> int:
        if wf is None or not wf.timeout_seconds:
            return DEFAULT_WORK_TIMEOUT_SECONDS
        return wf.timeout_seconds

    def _context(self, node_id: str) -> dict:
        runs = self.uow.runs.list_by_node(self.task.task_id, node_id)
        latest = max(runs, key=lambda item: item.attempt_no) if runs else None
        return {
            "result": parse_result(latest.result) if latest else None,
            "task": {"title": self.task.title, "state": self.task.state.value,
                     "workflow_id": self.task.workflow_id},
            "node": {"node_id": node_id, "name": self.nodes[node_id].name},
            "context": {},
            "artifacts": len(self.uow.artifacts.list_by_task(self.task.task_id)),
        }

    def _mark_running(self) -> None:
        if self.task.state not in (TaskState.RUNNING, TaskState.DONE, TaskState.CANCELLED):
            self._save_task(replace(self.task, state=TaskState.RUNNING))

    def _save_task(self, task: Task) -> None:
        self.task = replace(task, updated_at=self.clock.now())
        self.uow.tasks.save_task(self.task)

    def _save_node(self, node: TaskNode) -> None:
        self.nodes[node.node_id] = replace(node, updated_at=self.clock.now())
        self.uow.tasks.save_node(self.nodes[node.node_id])

    def _withdraw_approvals(self, node_id: str | None = None,
                            keep_decision: bool = False) -> None:
        for item in self.uow.approvals.list_all(None, self.task.task_id):
            if item.status is not ApprovalStatus.PENDING:
                continue
            if node_id is not None and item.node_id != node_id:
                continue
            self.uow.approvals.save(replace(
                item, status=ApprovalStatus.WITHDRAWN,
                resolved_by=self.task.created_by, resolved_at=self.clock.now()))
