"""Pipeline 步骤改派兜底 — 按 role_type 同工种/相近工种切换，禁止硬编码人名链。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Set, Tuple

from lib.composition import get_fsm, get_locale
from lib.domain.models import Inbox, MsgStatus
from lib.application.orchestration.pipeline.trigger import _send_task


def _fsm():
    return get_fsm()


def _locale(data_dir: str = ""):
    return get_locale(data_dir)
from lib.application.orchestration.tracker import TaskTracker
from lib.infra.utils import json_read, json_write, resolve_paths, _now_iso
from .role_resolver import resolve_agent_for_role_type
from .tier_filter import dispatch_action_from_envelope

# 步骤 role_type → 相近工种 role_type 优先级（后者可顶班）
DEFAULT_SIMILAR_ROLE_TYPES: Dict[int, List[int]] = {
    5: [8, 1],   # 审查官 → 开发工程师 → 方案设计师（架构）
    6: [8, 5],   # 测试 → 开发 → 审查
    8: [8, 1],   # 开发 → 其他开发 → 架构
}


def _pipeline_ops(config: Optional[dict]) -> dict:
    return (config or {}).get("pipeline_ops") or {}


def failover_enabled(config: Optional[dict] = None) -> bool:
    ops = _pipeline_ops(config)
    return ops.get("failover_on_max_pushes", True) is not False


def max_failures_per_step(config: Optional[dict] = None) -> int:
    """同 step 连续失败阈值（默认 2，SoT: role_failover.json）。"""
    ops = _pipeline_ops(config)
    rf = ops.get("role_failover") or {}
    if isinstance(rf, dict) and rf.get("max_failures_per_step") is not None:
        return int(rf["max_failures_per_step"])
    if ops.get("max_failures_per_step") is not None:
        return int(ops["max_failures_per_step"])
    return 2


def record_step_delivery_failure(step: dict, config: Optional[dict] = None) -> bool:
    """
    记录一步交付失败；返回是否应触发 failover（≥ max_failures_per_step）。
    """
    step["delivery_failures"] = int(step.get("delivery_failures") or 0) + 1
    return step["delivery_failures"] >= max_failures_per_step(config)


def should_failover_after_failures(step: dict, config: Optional[dict] = None) -> bool:
    """只读判定：当前失败计数是否已达改派阈值。"""
    return int(step.get("delivery_failures") or 0) >= max_failures_per_step(config)


def silent_failure_config(config: Optional[dict]) -> dict:
    sf = _pipeline_ops(config).get("silent_failure") or {}
    return sf if isinstance(sf, dict) else {}


def silent_failure_minutes(config: Optional[dict], data_dir: str = "") -> float:
    if config is None and data_dir:
        config = json_read(os.path.join(data_dir, "config.json"), {})
    sf = silent_failure_config(config)
    return float(sf.get("minutes", 8))


def role_failover_plan(step_role_type: int, config: Optional[dict] = None) -> List[int]:
    """
    返回按优先级尝试的 role_type 列表：先同工种，再相近工种。
    配置覆盖：pipeline_ops.role_failover.{role_type}.similar_role_types
    """
    rt = int(step_role_type)
    ops = _pipeline_ops(config)
    rf = ops.get("role_failover") or {}
    spec = rf.get(str(rt)) or rf.get(rt) or {}

    similar: List[int] = []
    raw_similar = spec.get("similar_role_types")
    if isinstance(raw_similar, list) and raw_similar:
        similar = [int(x) for x in raw_similar]
    else:
        similar = list(DEFAULT_SIMILAR_ROLE_TYPES.get(rt, []))

    plan: List[int] = []
    if spec.get("same_role", True):
        plan.append(rt)
    for srt in similar:
        if int(srt) not in plan:
            plan.append(int(srt))
    return plan


def _agent_dispatchable(data_dir: str, agent: str, agents_cfg: dict) -> bool:
    if not agent:
        return False
    if agent in agents_cfg:
        if agents_cfg[agent].get("available") is False:
            return False
        return True
    paths = resolve_paths(data_dir)
    return os.path.isdir(os.path.join(paths["inbox"], agent))


def next_failover_agent_for_step(
    data_dir: str,
    task: dict,
    config: Optional[dict] = None,
) -> Optional[Tuple[str, dict]]:
    """
    为当前 running 步骤按工种选取下一个 agent。
    返回 (agent_id, dispatch_meta)；无可用则 None。
    """
    if config is None:
        config = json_read(os.path.join(data_dir, "config.json"), {})
    if not failover_enabled(config):
        return None

    step = get_fsm().get_active_step(task)
    if not step or step.get("status") != "running":
        return None

    step_rt = step.get("role_type")
    if step_rt is None:
        return None
    step_rt = int(step_rt)

    current = step.get("to_agent") or step.get("to_person") or task.get("assignee") or ""
    tried: Set[str] = set(step.get("failover_tried") or [])
    if current:
        tried.add(current)

    agents_cfg = config.get("agents") or {}
    action = dispatch_action_from_envelope(task)
    plan = role_failover_plan(step_rt, config)

    for plan_rt in plan:
        candidates = [
            c for c in _locale(data_dir).role_type_candidates(plan_rt)
            if c not in tried and _agent_dispatchable(data_dir, c, agents_cfg)
        ]
        if not candidates:
            continue
        agent_id, meta = resolve_agent_for_role_type(
            data_dir,
            plan_rt,
            exclude=tried,
            action=action,
            agents_cfg=agents_cfg,
        )
        if not agent_id or agent_id in tried:
            continue
        if not _agent_dispatchable(data_dir, agent_id, agents_cfg):
            continue
        tier = "same_role" if plan_rt == step_rt else "similar_role"
        meta = dict(meta or {})
        meta.update({
            "failover_tier": tier,
            "failover_from_role_type": step_rt,
            "failover_to_role_type": plan_rt,
            "failover_to_role_zh": _locale(data_dir).role_type_to_zh(plan_rt),
            "failover_plan": plan,
        })
        return agent_id, meta

    return None


def _close_agent_task_inbox(data_dir: str, agent: str, task_id: str) -> int:
    paths = resolve_paths(data_dir)
    inbox_file = os.path.join(paths["inbox"], agent, "inbox.json")
    if not os.path.isfile(inbox_file):
        return 0
    inbox = Inbox.from_dict(json_read(inbox_file, {}))
    closed = 0
    for m in inbox.messages:
        content = inbox.msg_field(m, "content", "") or ""
        if task_id not in content and inbox.msg_field(m, "task_id", "") != task_id:
            continue
        mid = inbox.msg_field(m, "id", "")
        state = (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")).lower()
        if state in ("done", "closed", "archived"):
            continue
        inbox.set_msg_status(
            mid, MsgStatus.CLOSED, state=MsgStatus.CLOSED,
            done_at=_now_iso(), done_note=f"failover closed for {task_id}",
        )
        closed += 1
    if closed:
        json_write(inbox_file, inbox.to_dict())
    return closed


def _step_summary_for_dispatch(data_dir: str, task_id: str, step: dict) -> str:
    step_num = int(step.get("step") or 0)
    prev_id = f"s{max(step_num - 1, 1)}"
    prev = get_fsm().read_step_result(data_dir, task_id, {"step_id": prev_id})
    if prev and prev.get("summary"):
        return str(prev["summary"])
    if step.get("summary"):
        return str(step["summary"])
    role = step.get("to_role") or "当前工种"
    return f"继续 pipeline {task_id}：完成当前步骤（{role}），读取任务文件并写入 step 结果。"


def failover_pipeline_step(
    data_dir: str,
    task_id: str,
    *,
    reason: str,
    from_agent: Optional[str] = None,
) -> Optional[str]:
    """
    将 running pipeline 当前步骤改派到同工种/相近工种 agent，并创建新 inbox 工单。
    成功返回新 agent；无法 failover 返回 None。
    """
    tr = TaskTracker(data_dir)
    task = tr.get(task_id)
    if not task or task.get("status") != "running":
        return None
    config = json_read(os.path.join(data_dir, "config.json"), {})
    step = get_fsm().get_active_step(task)
    if not step:
        return None

    old_agent = from_agent or step.get("to_agent") or step.get("to_person") or ""
    picked = next_failover_agent_for_step(data_dir, task, config)
    if not picked:
        return None
    new_agent, failover_meta = picked

    step_num = int(step.get("step") or 0)
    step_id = step.get("step_id") or f"s{step_num}"
    tried = list(step.get("failover_tried") or [])
    if old_agent and old_agent not in tried:
        tried.append(old_agent)

    dispatch_meta = {
        "method": "pipeline_role_failover",
        "reason": reason,
        "failover_from": old_agent,
        "failover_at": _now_iso(),
        **failover_meta,
    }

    for s in task.get("chain") or []:
        if s.get("step") != step_num:
            continue
        s["failover_tried"] = tried
        s["pin_agent"] = new_agent
        s["to_agent"] = new_agent
        s["to_person"] = new_agent
        s["dispatch_meta"] = dispatch_meta
        if failover_meta.get("failover_to_role_type") is not None:
            s["role_type"] = failover_meta["failover_to_role_type"]
        break

    task["assignee"] = new_agent
    task["updated_at"] = _now_iso()
    json_write(os.path.join(tr.tasks_dir, f"{task_id}.json"), task)

    if old_agent:
        _close_agent_task_inbox(data_dir, old_agent, task_id)

    paths = resolve_paths(data_dir)
    summary = _step_summary_for_dispatch(data_dir, task_id, step)
    to_role = failover_meta.get("failover_to_role_zh") or step.get("to_role") or ""
    ok = _send_task(
        data_dir,
        paths,
        from_person=step.get("from_agent") or "mailbus",
        from_role=step.get("from_role") or "",
        to_role=to_role,
        to_person=new_agent,
        summary=summary,
        task_id=task_id,
        step_num=step_num,
        step_id=step_id,
        result_ref=step.get("result_ref"),
    )
    if not ok:
        return None
    return new_agent


def try_failover_on_delivery_failure(
    data_dir: str,
    task_id: str,
    msg_id: str,
    *,
    reason: str,
    old_agent: str,
) -> Optional[str]:
    """推送/催办耗尽时尝试 pipeline 工种 failover。"""
    if not failover_enabled(json_read(os.path.join(data_dir, "config.json"), {})):
        return None
    return failover_pipeline_step(
        data_dir, task_id, reason=f"{reason} msg={msg_id}", from_agent=old_agent,
    )


def note_pipeline_verify_failure(
    data_dir: str,
    task_id: str,
    agent_name: str,
    msg_id: str,
    *,
    reason: str,
) -> Optional[str]:
    """
    交付校验失败：递增 step.delivery_failures 并持久化；
    达阈值时触发同工种 failover。返回新 agent（若改派）。
    """
    config = json_read(os.path.join(data_dir, "config.json"), {})
    tr = TaskTracker(data_dir)
    task = tr.get(task_id)
    if not task:
        return None
    step = get_fsm().get_active_step(task)
    if not step:
        return None
    should_failover = record_step_delivery_failure(step, config)
    json_write(os.path.join(tr.tasks_dir, f"{task_id}.json"), task)
    if should_failover:
        return try_failover_on_delivery_failure(
            data_dir, task_id, msg_id, reason=reason, old_agent=agent_name,
        )
    return None


def try_silent_failure_failover(
    data_dir: str,
    task_id: str,
    agent_name: str,
    msg_id: str,
    *,
    age_min: float,
) -> Optional[str]:
    """
    静默失败（CLI 已退出、无 step 结果、无 API reply）→ 按工种 failover。
    默认推送后 8 分钟触发；可用 pipeline_ops.silent_failure.minutes 配置。
    """
    config = json_read(os.path.join(data_dir, "config.json"), {})
    sf = silent_failure_config(config)
    if sf.get("enabled", True) is False:
        return None
    if age_min < silent_failure_minutes(config):
        return None

    from ..pipeline_result_check import pipeline_step_result_matches

    task = TaskTracker(data_dir).get(task_id)
    if not task:
        return None
    ok, _ = pipeline_step_result_matches(data_dir, task, agent_name)
    if ok:
        return None

    max_attempts = int(sf.get("max_failovers_per_step", 3))
    step = get_fsm().get_active_step(task) or {}
    if len(step.get("failover_tried") or []) >= max_attempts:
        return None

    from ..alerter import push_alert

    new_agent = failover_pipeline_step(
        data_dir,
        task_id,
        reason=f"silent_failure msg={msg_id}",
        from_agent=agent_name,
    )
    if new_agent:
        push_alert(
            data_dir,
            "silent_failure_failover",
            "warn",
            agent_name,
            (
                f"静默失败已按工种改派：{agent_name} → {new_agent}（task={task_id}）。"
                f" 原因：推送后 {age_min:.0f}min 无 step 结果且 CLI 已退出。"
                f" 舰队监控 → 告警"
            ),
            dedupe_key=f"silent_failure:{task_id}:{msg_id}",
        )
    return new_agent



