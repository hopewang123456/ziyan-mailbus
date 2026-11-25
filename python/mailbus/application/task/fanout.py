"""扇出、汇聚与分片重试：Flow 的派发细分实现（组合进 Flow）。"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

from mailbus.application.task import staff
from mailbus.core.identity.values import AccountType
from mailbus.core.workflow.models import TaskRun
from mailbus.core.workflow.values import (
    NodeState,
    RunState,
    TERMINAL_RUN_STATES,
)


def latest_by_slot(runs) -> list[TaskRun]:
    """同一槽位取 attempt 最大的一条，扇出分片独立重试后仍是单条。"""
    latest: dict[int, TaskRun] = {}
    for run in runs:
        current = latest.get(run.fanout_slot)
        if current is None or run.attempt_no > current.attempt_no:
            latest[run.fanout_slot] = run
    return list(latest.values())


class FanoutMixin:
    # 由 Flow 注入的属性
    uow: object
    task: object
    graph: object
    nodes: dict
    ids: object
    clock: object

    def _dispatch_agent(self, node, wf, parent: str | None = None) -> None:
        candidates = staff.pick_candidates(
            self.uow, wf, AccountType.AGENT, self.clock.now()
        )
        if not candidates:
            return
        now = self.clock.now()
        fanout = max(1, int(wf.config.get("fanout") or 1))
        # 候选不足 N 人时按现有候选开跑并标记 short_fanout，缺口计入 join 的 missing。
        short = fanout > 1 and len(candidates) < fanout
        workers = candidates[:fanout]
        attempt = self.uow.runs.max_attempt(self.task.task_id, node.node_id) + 1
        group = f"{self.task.task_id}:{node.node_id}:{attempt}" if fanout > 1 else None
        slots = range(1, len(workers) + 1) if fanout > 1 else [0]
        latest = None
        for slot, employee in zip(slots, workers):
            run = TaskRun(
                run_id=self.ids.new("run"), task_id=self.task.task_id,
                node_id=node.node_id, attempt_no=attempt, state=RunState.DISPATCHED,
                fanout_slot=slot, assigned_employee_id=employee.employee_id,
                fanout_group=group, short_fanout=short, parent_run_id=parent,
                dispatched_at=now,
                deadline_at=now + timedelta(seconds=self._timeout(wf)),
            )
            self.uow.runs.add(run)
            latest = run
        self._save_node(replace(node, state=NodeState.RUNNING,
                                current_run_id=latest.run_id if latest else None))
        self._mark_running()

    def _retry_slot(self, run: TaskRun, wf) -> None:
        """扇出分片独立重试：沿用原执行人与槽位，仅递增 attempt。"""
        now = self.clock.now()
        attempt = self.uow.runs.max_attempt(self.task.task_id, run.node_id) + 1
        fresh = replace(
            run, run_id=self.ids.new("run"), attempt_no=attempt,
            state=RunState.DISPATCHED, result=None, started_at=None,
            completed_at=None, dispatched_at=now,
            deadline_at=now + timedelta(seconds=self._timeout(wf)),
        )
        self.uow.runs.add(fresh)
        self._save_node(replace(self.nodes[run.node_id], state=NodeState.RUNNING,
                                current_run_id=fresh.run_id))

    def join_state(self, node_id: str) -> tuple[bool, list[str]]:
        """按「每个槽位的最新 attempt」判断汇聚；缺口不自动推进，交 rerun-join。"""
        runs = self.uow.runs.list_by_task(self.task.task_id)
        missing: list[str] = []
        ready = True
        for pred in self.graph.predecessors(node_id) if self.graph else []:
            pred_runs = [item for item in runs if item.node_id == pred]
            if not pred_runs:
                missing.append(f"{pred}:none")
                ready = False
                continue
            latest = latest_by_slot(pred_runs)
            fanout = self._fanout(pred)
            if fanout > 1 and len(latest) < fanout and not any(
                    item.short_fanout for item in latest):
                missing.append(f"{pred}:short")
                ready = False
            for item in latest:
                if item.state not in TERMINAL_RUN_STATES:
                    ready = False
                if item.state in (RunState.FAILED, RunState.SKIPPED):
                    slot = f":slot{item.fanout_slot}" if fanout > 1 else ""
                    missing.append(f"{pred}{slot}:{item.state.value}")
                    ready = False
        return ready, missing

    def _join(self, node_id: str) -> None:
        node = self.nodes[node_id]
        ready, missing = self.join_state(node_id)
        if not ready:
            self._save_node(replace(node, state=NodeState.PENDING, current_run_id=None))
            return
        now = self.clock.now()
        attempt = self.uow.runs.max_attempt(self.task.task_id, node_id) + 1
        run = TaskRun(
            run_id=self.ids.new("run"), task_id=self.task.task_id, node_id=node_id,
            attempt_no=attempt, state=RunState.DONE, dispatched_at=now,
            started_at=now, completed_at=now,
            result=json.dumps({"missing": missing, "forced": False}, ensure_ascii=False),
        )
        self.uow.runs.add(run)
        self._save_node(replace(node, state=NodeState.DONE, current_run_id=run.run_id))
        self.advance(node_id)
        self.settle()

    def force_join(self, node_id: str, group: str, scope: str) -> list[str]:
        """人工显式补跑汇聚：记录 missing 范围，必要时继续推进下游。"""
        _, missing = self.join_state(node_id)
        now = self.clock.now()
        attempt = self.uow.runs.max_attempt(self.task.task_id, node_id) + 1
        run = TaskRun(
            run_id=self.ids.new("run"), task_id=self.task.task_id, node_id=node_id,
            attempt_no=attempt, state=RunState.DONE, dispatched_at=now,
            started_at=now, completed_at=now,
            result=json.dumps({"missing": missing, "forced": True,
                               "fanout_group": group, "scope": scope},
                              ensure_ascii=False),
        )
        self.uow.runs.add(run)
        self.last_attempt = attempt
        self._save_node(replace(self.nodes[node_id], state=NodeState.DONE,
                                current_run_id=run.run_id))
        if scope == "downstream":
            self.advance(node_id)
        self.settle()
        return missing

    def _slots_settled(self, node_id: str) -> bool:
        latest = latest_by_slot(
            self.uow.runs.list_by_node(self.task.task_id, node_id))
        return bool(latest) and all(
            item.state in TERMINAL_RUN_STATES for item in latest)

    def _fanout_state(self, node_id: str) -> NodeState:
        """扇出聚合态：全部槽位 done 才算成功，否则标记失败供 join 记 missing。"""
        latest = latest_by_slot(
            self.uow.runs.list_by_node(self.task.task_id, node_id))
        if latest and all(item.state is RunState.DONE for item in latest):
            return NodeState.DONE
        return NodeState.FAILED
