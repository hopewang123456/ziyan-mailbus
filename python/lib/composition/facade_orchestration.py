"""Composition facades — orchestration domain (R2 split).

Target domain: adapters.orchestration.* + application.orchestration/pipeline/role_flow/
workflow/harness/commands bridges (FSM / human queue / pipeline / role flow / automation).
"""
from __future__ import annotations

from typing import Any


def human_queue_path(data_dir: str) -> str:
    from lib.adapters.orchestration.human_queue import queue_path

    return queue_path(data_dir)


def is_phantom_reply_text(*args: Any, **kwargs: Any) -> bool:
    from lib.application.orchestration.phantom_detect import is_phantom_reply_text as _fn

    return bool(_fn(*args, **kwargs))


def is_task_complete(
    data_dir: str,
    agent_name: str,
    msg_entry: dict,
    *,
    agent_type: str = "",
    reply_text: str = "",
):
    """任务完成判定 — adapter 通过本函数拿到 application 服务，避免 adapter→application 跨层违规。

    实际实现见 `lib.application.orchestration.task_completion.is_task_complete`。
    """
    from lib.application.orchestration.task_completion import is_task_complete as _impl

    return _impl(
        data_dir, agent_name, msg_entry, agent_type=agent_type, reply_text=reply_text,
    )


def check_phantom_completion(*args: Any, **kwargs: Any):
    """Phantom completion 检测 — 委托给 adapter，adapter 通过 is_task_complete
    拿到 application 服务（composition 隔离跨层依赖）。"""
    from lib.application.orchestration.phantom_detect import check_phantom_completion as _fn

    return _fn(*args, **kwargs)


def resolve_human_queue_item(*args: Any, **kwargs: Any):
    """Human gate 队列项解析 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.human_queue_resolve.resolve_human_queue_item`。
    """
    from lib.application.orchestration.human_queue_resolve import resolve_human_queue_item as _impl

    return _impl(*args, **kwargs)


def get_system_message(*args: Any, **kwargs: Any):
    """新 agent 上线系统消息模板 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.commands.commands.get_system_message`。
    """
    from lib.application.commands.commands import get_system_message as _impl

    return _impl(*args, **kwargs)


def attach_mailbus_routing(*args: Any, **kwargs: Any):
    """Mailbus 路由附加 — core/a2a 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.complexity_router.attach_mailbus_routing`。
    """
    from lib.adapters.llm_routing.complexity_router import attach_mailbus_routing as _impl

    return _impl(*args, **kwargs)


def load_human_queue(*args: Any, **kwargs: Any):
    """Human queue 加载 — core/a2a 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.human_queue.load_queue`。
    """
    from lib.adapters.orchestration.human_queue import load_queue as _impl

    return _impl(*args, **kwargs)


def poll_pending_a2a_tasks(*args: Any, **kwargs: Any):
    """A2A 轮询 — core/a2a 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.a2a_poll.poll_pending_a2a_tasks`。
    """
    from lib.application.orchestration.a2a_poll import poll_pending_a2a_tasks as _impl

    return _impl(*args, **kwargs)


def get_harness(*args: Any, **kwargs: Any):
    """Harness 工厂 — core/a2a 通过本函数拿到 application 服务。

    实际实现见 `lib.application.harness.get_harness`。
    """
    from lib.application.harness import get_harness as _impl

    return _impl(*args, **kwargs)


def enqueue_human_queue(*args: Any, **kwargs: Any):
    """Human queue 入队 — core/a2a 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.human_queue.enqueue`。
    """
    from lib.adapters.orchestration.human_queue import enqueue as _impl

    return _impl(*args, **kwargs)


def apply_cancel(*args: Any, **kwargs: Any):
    """Task cancel — api/handlers_a2a 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.apply_cancel`。
    """
    from lib.application.orchestration.task_fsm import apply_cancel as _impl

    return _impl(*args, **kwargs)


def apply_pause(*args: Any, **kwargs: Any):
    """Task pause — api/handlers_tasks 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.apply_pause`。
    """
    from lib.application.orchestration.task_fsm import apply_pause as _impl

    return _impl(*args, **kwargs)


def apply_rollback(*args: Any, **kwargs: Any):
    """Task rollback — api/handlers_tasks 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.apply_rollback`。
    """
    from lib.application.orchestration.task_fsm import apply_rollback as _impl

    return _impl(*args, **kwargs)


def apply_skip(*args: Any, **kwargs: Any):
    """Task skip — api/handlers_tasks 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.apply_skip`。
    """
    from lib.application.orchestration.task_fsm import apply_skip as _impl

    return _impl(*args, **kwargs)


def apply_approve_join(*args: Any, **kwargs: Any):
    """Collab join_gate=review 管理者批准。"""
    from lib.application.orchestration.task_fsm import apply_approve_join as _impl

    return _impl(*args, **kwargs)


def ensure_fsm(*args: Any, **kwargs: Any):
    """Task FSM ensure — api/handlers_tasks 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.ensure_fsm`。
    """
    from lib.application.orchestration.task_fsm import ensure_fsm as _impl

    return _impl(*args, **kwargs)


def fsm_summary(*args: Any, **kwargs: Any):
    """Task FSM summary — api/handlers_tasks 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.fsm_summary`。
    """
    from lib.application.orchestration.task_fsm import fsm_summary as _impl

    return _impl(*args, **kwargs)


def mark_step_dispatched(*args: Any, **kwargs: Any):
    """Task step dispatch 标记 — api/handlers_tasks 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.mark_step_dispatched`。
    """
    from lib.application.orchestration.task_fsm import mark_step_dispatched as _impl

    return _impl(*args, **kwargs)


def resolve_transition(*args: Any, **kwargs: Any):
    """fsm 步骤转移解析（role/person/kind）— application 经此访问（分层约束）。"""
    from lib.application.orchestration.task_fsm import resolve_transition as _impl

    return _impl(*args, **kwargs)


def create_next_step(*args: Any, **kwargs: Any):
    """fsm 创建下一步骤 — application 经此访问（分层约束）。"""
    from lib.application.orchestration.task_fsm import create_next_step as _impl

    return _impl(*args, **kwargs)


def push_gate(*args: Any, **kwargs: Any):
    """E2 push 预算查询 — application 层经此访问（分层约束）。"""
    from lib.adapters.orchestration.automation import push_gate as _impl

    return _impl(*args, **kwargs)


def bump_push_count(*args: Any, **kwargs: Any):
    """E2 push 计数 — application 层经此访问（分层约束）。"""
    from lib.adapters.orchestration.automation import bump_push_count as _impl

    return _impl(*args, **kwargs)


def push_budget_blocked(*args: Any, **kwargs: Any):
    """E2 push 预算熔断 — application 层经此访问（分层约束）。"""
    from lib.adapters.orchestration.automation import push_budget_blocked as _impl

    return _impl(*args, **kwargs)


def should_auto_approve_plan(*args: Any, **kwargs: Any) -> bool:
    from lib.adapters.orchestration.automation import should_auto_approve_plan as _fn

    return bool(_fn(*args, **kwargs))


def run_scan_once(*args: Any, **kwargs: Any):
    """bus scan 执行一轮 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.commands.commands.run_scan_once`。
    """
    from lib.application.commands.commands import run_scan_once as _impl

    return _impl(*args, **kwargs)


def task_tracker_factory():
    """TaskTracker 工厂 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.tracker.TaskTracker`。
    adapter 不直接 import tracker 子树（避免跨层违规）。
    """
    from lib.application.orchestration.tracker import TaskTracker

    return TaskTracker


def bridge_reconcile(*args: Any, **kwargs: Any):
    """Bridge 协调 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.workflow.intake.spawn_rules.bridge_reconcile`。
    """
    from lib.application.workflow.intake.spawn_rules import bridge_reconcile as _impl

    return _impl(*args, **kwargs)


# ── task_fsm.py 跨层调用（adapter→application 解耦，2026-09 治理）────────────


def trigger_task(*args: Any, **kwargs: Any):
    """Pipeline 任务触发 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.pipeline.trigger.trigger_task`。
    """
    from lib.application.orchestration.pipeline.trigger import trigger_task as _impl

    return _impl(*args, **kwargs)


def resolve_next_assignee(*args: Any, **kwargs: Any):
    """Pipeline 下一步执行者解析 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.pipeline.routing.resolve_next_assignee`。
    """
    from lib.application.orchestration.pipeline.routing import resolve_next_assignee as _impl

    return _impl(*args, **kwargs)


def is_pipeline_terminal(*args: Any, **kwargs: Any):
    """Pipeline 终止判定 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.pipeline.routing.is_pipeline_terminal`。
    """
    from lib.application.orchestration.pipeline.routing import is_pipeline_terminal as _impl

    return _impl(*args, **kwargs)


def run_step_verify(*args: Any, **kwargs: Any):
    """Step verify 执行 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.ops.verify.runner.run_step_verify`。
    """
    from lib.application.ops.verify.runner import run_step_verify as _impl

    return _impl(*args, **kwargs)


def notify_verify_failure(*args: Any, **kwargs: Any):
    """Verify 失败升级通知 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.harness.escalation.notify_verify_failure`。
    """
    from lib.application.harness.escalation import notify_verify_failure as _impl

    return _impl(*args, **kwargs)


def block_for_clarifications(*args: Any, **kwargs: Any):
    """阻塞等待澄清 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.decomposition.block_for_clarifications`。
    """
    from lib.application.orchestration.decomposition import block_for_clarifications as _impl

    return _impl(*args, **kwargs)


def handle_design_step_decomposition(*args: Any, **kwargs: Any):
    """设计步骤拆解 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.decomposition.handle_design_step_decomposition`。
    """
    from lib.application.orchestration.decomposition import handle_design_step_decomposition as _impl

    return _impl(*args, **kwargs)


def maybe_block_after_step(*args: Any, **kwargs: Any):
    """Step 后置阻塞判定 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.workflow.engine.maybe_block_after_step`。
    """
    from lib.application.workflow.engine import maybe_block_after_step as _impl

    return _impl(*args, **kwargs)


def enter_accepting_or_succeed(*args: Any, **kwargs: Any):
    """进入 accepting 状态 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.actions.enter_accepting_or_succeed`。
    """
    from lib.application.orchestration.actions import enter_accepting_or_succeed as _impl

    return _impl(*args, **kwargs)


def get_next_role(*args: Any, **kwargs: Any):
    """下一角色判定 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.role_flow.get_next_role`。
    """
    from lib.application.orchestration.role_flow import get_next_role as _impl

    return _impl(*args, **kwargs)


def next_role_after(*args: Any, **kwargs: Any):
    """步骤内下一跳裁决（role-flow SoT 优先，legacy 兜底）— 跨层唯一入口。

    实际实现见 `lib.application.orchestration.role_flow.next_role_after`。
    """
    from lib.application.orchestration.role_flow import next_role_after as _impl

    return _impl(*args, **kwargs)


def pick_person_for_role(*args: Any, **kwargs: Any):
    """角色指派 agent 选择 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.role_flow.pick_person_for_role`。
    """
    from lib.application.orchestration.role_flow import pick_person_for_role as _impl

    return _impl(*args, **kwargs)


__all__ = [
    "human_queue_path",
    "is_phantom_reply_text",
    "is_task_complete",
    "check_phantom_completion",
    "resolve_human_queue_item",
    "get_system_message",
    "attach_mailbus_routing",
    "load_human_queue",
    "poll_pending_a2a_tasks",
    "get_harness",
    "enqueue_human_queue",
    "apply_cancel",
    "apply_pause",
    "apply_rollback",
    "apply_skip",
    "apply_approve_join",
    "ensure_fsm",
    "fsm_summary",
    "mark_step_dispatched",
    "resolve_transition",
    "create_next_step",
    "push_gate",
    "bump_push_count",
    "push_budget_blocked",
    "bump_retry_count",
    "retry_exceeded",
    "verify_fail_auto_retry",
    "position_catalog",
    "should_auto_approve_plan",
    "run_scan_once",
    "task_tracker_factory",
    "bridge_reconcile",
    "trigger_task",
    "resolve_next_assignee",
    "is_pipeline_terminal",
    "run_step_verify",
    "notify_verify_failure",
    "block_for_clarifications",
    "handle_design_step_decomposition",
    "maybe_block_after_step",
    "enter_accepting_or_succeed",
    "get_next_role",
    "next_role_after",
    "pick_person_for_role",
]


def bump_retry_count(*args: Any, **kwargs: Any):
    """自动重试计数 — application/task_fsm 经此访问（分层约束）。"""
    from lib.adapters.orchestration.automation import bump_retry_count as _impl

    return _impl(*args, **kwargs)


def retry_exceeded(*args: Any, **kwargs: Any):
    """重试上限判定 — application/task_fsm 经此访问（分层约束）。"""
    from lib.adapters.orchestration.automation import retry_exceeded as _impl

    return _impl(*args, **kwargs)


def verify_fail_auto_retry(*args: Any, **kwargs: Any):
    """verify 失败自动重试判定 — application/task_fsm 经此访问（分层约束）。"""
    from lib.adapters.orchestration.automation import verify_fail_auto_retry as _impl

    return _impl(*args, **kwargs)


def position_catalog(*args: Any, **kwargs: Any):
    """职位目录（D3 职位≠角色）— api/handlers_system 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.dispatch.role_resolver.position_catalog`。
    """
    from lib.application.orchestration.dispatch.role_resolver import position_catalog as _impl

    return _impl(*args, **kwargs)
