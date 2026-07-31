"""pipeline 任务消息识别与推送约束（防只 ack 不执行）。"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

from lib.application.orchestration.pipeline.step import (
    is_v3_task,
    planned_agents_remaining,
    planned_role_types_remaining,
    step_agent,
    step_role_type,
    step_role_zh,
)

_TASK_ID_RE = re.compile(r"【([a-zA-Z0-9_-]+)】")


def extract_task_id(content: str) -> Optional[str]:
    m = _TASK_ID_RE.search(content or "")
    return m.group(1) if m else None


def get_running_pipeline_task(data_dir: str, task_id: str) -> Optional[dict]:
    from .tracker import TaskTracker

    t = TaskTracker(data_dir).get(task_id)
    if not t or t.get("status") != "running":
        return None
    chain = t.get("chain") or []
    if not chain or not isinstance(chain[0], dict):
        return None
    return t


def is_current_pipeline_assignee(data_dir: str, task_id: str, agent_name: str) -> bool:
    """chain 当前 running 步骤是否指派给该 agent。"""
    t = get_running_pipeline_task(data_dir, task_id)
    if not t:
        return False
    cur = (t.get("chain") or [])[-1]
    agent_ok = cur.get("to_agent") == agent_name or cur.get("to_person") == agent_name
    return agent_ok and cur.get("status") == "running"


def primary_pipeline_assignee(data_dir: str) -> Optional[str]:
    """iteration primary 任务当前 chain 步骤 assignee（running 时）。"""
    try:
        from .iteration_engine import load_primary_task_id
    except ImportError:
        return None
    primary = load_primary_task_id(data_dir)
    if not primary:
        return None
    t = get_running_pipeline_task(data_dir, primary)
    if not t:
        return None
    cur = (t.get("chain") or [])[-1]
    if cur.get("status") != "running":
        return None
    return cur.get("to_agent") or cur.get("to_person") or None


def side_audit_deferred_for_reviewer(data_dir: str, reviewer: str) -> bool:
    """主 pipeline running 时暂停全部 Round1 side-audit（Codex 单槽不与主链争用）。"""
    return bool(primary_pipeline_assignee(data_dir))


def pipeline_inbox_may_mark_done(
    data_dir: str, agent_name: str, msg_entry: dict,
) -> tuple[bool, str]:
    """pipeline 执行工单：无 verify 通过不得标 done/closed。"""
    if not is_pipeline_execute_message(msg_entry, data_dir):
        return True, "not_pipeline"
    ok, reason = verify_pipeline_step_delivery(data_dir, agent_name, msg_entry)
    return ok, reason


def is_side_audit_message(msg_id: str) -> bool:
    return str(msg_id or "").startswith("audit-req-")


def pipeline_inbox_message_stale(data_dir: str, agent_name: str, content: str) -> bool:
    """该 agent 不应再执行此 pipeline 工单（已完成本步或已不是当前 assignee）。"""
    tid = extract_task_id(content or "")
    if not tid:
        return False
    t = get_running_pipeline_task(data_dir, tid)
    if not t:
        return True
    chain = t.get("chain") or []
    cur = chain[-1] if chain else {}
    if (cur.get("to_agent") == agent_name or cur.get("to_person") == agent_name) and cur.get("status") == "running":
        return False
    for step in chain:
        sa = step.get("to_agent") or step.get("to_person")
        if sa == agent_name and step.get("status") in ("completed", "done"):
            return True
    cur_agent = cur.get("to_agent") or cur.get("to_person")
    return cur_agent != agent_name


def pipeline_message_protected_from_auto_close(
    data_dir: str,
    agent_name: str,
    m_raw: Any,
    inbox: Any = None,
) -> bool:
    """当前 running pipeline 执行工单：禁止催办 3 次 / max_pushes 自动关闭。"""
    if inbox is not None:
        msg_type = inbox.msg_field(m_raw, "type", "")
        content = inbox.msg_field(m_raw, "content", "")
    elif isinstance(m_raw, dict):
        msg_type = m_raw.get("type", "")
        content = m_raw.get("content", "")
    else:
        return False
    if msg_type != "task":
        return False
    entry = m_raw if isinstance(m_raw, dict) else {}
    if is_pipeline_execute_message(entry, data_dir):
        return True
    tid = extract_task_id(content or "") or entry.get("task_id")
    if tid and is_current_pipeline_assignee(data_dir, tid, agent_name):
        return True
    return False


def is_pipeline_execute_message(msg: Any, data_dir: str) -> bool:
    """消息是否对应当前 running pipeline 步骤（须写 msg-results，禁止 auto_ack）。"""
    content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
    tid = extract_task_id(content or "")
    if not tid:
        return False
    t = get_running_pipeline_task(data_dir, tid)
    if not t:
        return False
    chain = t.get("chain") or []
    cur = chain[-1]
    if cur.get("status") != "running":
        return False
    agent = msg.get("to") if isinstance(msg, dict) else getattr(msg, "to", "")
    if not agent:
        return True
    return (cur.get("to_agent") or cur.get("to_person")) == agent


def should_auto_ack_message(msg: Any, data_dir: str, agent_type: str) -> bool:
    """Hermes/OpenClaw：仅系统 notice 可 auto_ack；Cline/OpenCode 永不；pipeline 等 msg-results。"""
    from lib.agent_paths import type_supports_auto_ack
    from .model_router import is_no_llm_notice

    if not type_supports_auto_ack(agent_type):
        return False
    if is_pipeline_execute_message(msg, data_dir):
        return False
    mtype = msg.get("type", "notice") if isinstance(msg, dict) else getattr(msg, "type", "notice")
    if mtype in ("task", "task_reply", "question"):
        return False
    return is_no_llm_notice(msg)


def pipeline_completion_block(
    data_dir: str, content: str, agent_name: str, agent_cfg: dict | None = None,
) -> str:
    tid = extract_task_id(content or "")
    if not tid:
        return ""
    t = get_running_pipeline_task(data_dir, tid)
    if not t:
        return ""
    chain = t.get("chain") or []
    cur = chain[-1]
    sa = cur.get("to_agent") or cur.get("to_person")
    if sa != agent_name or cur.get("status") != "running":
        return ""
    step = cur.get("step") or len(chain)
    sid = cur.get("step_id")
    ref = cur.get("result_ref") or f"msg-results/{tid}.json"
    if ref.startswith("msg-results/"):
        rf = f"{data_dir}/{ref}"
    elif ref.startswith(data_dir):
        rf = ref
    else:
        rf = f"{data_dir}/msg-results/{tid}.json"
    if agent_cfg:
        from lib.agent_paths import store_path_for_agent

        rf = store_path_for_agent(data_dir, rf, agent_cfg)
    sid_part = f', "step_id":"{sid}"' if sid else ""
    return (
        f"\n[pipeline] 写结果→{rf}\n"
        f'{{"task_id":"{tid}","agent":"{agent_name}","pipeline_step":{step}'
        f'{sid_part},"conclusion":"done","summary":"≤200字","timestamp":"<ISO>"}}\n'
    )


def pipeline_has_more_steps(task: dict) -> bool:
    chain = task.get("chain") or []
    if planned_role_types_remaining(chain) or planned_agents_remaining(chain):
        return True
    cur = chain[-1] if chain else {}
    return cur.get("status") == "running"


def should_create_tracker_for_send(content: str, data_dir: str) -> bool:
    """bus send / API 推送：若内容已绑定 running pipeline task_id，不再用 msg.id 建 tracker。"""
    tid = extract_task_id(content or "")
    if not tid:
        return True
    if tid.startswith("msg-"):
        return True
    t = get_running_pipeline_task(data_dir, tid)
    if t and ((t.get("chain") or [{}])[0].get("planned_agents") is not None
              or (t.get("chain") or [{}])[0].get("planned_role_types") is not None):
        return False
    return True


def _read_ack_msg_ids(data_dir: str, agent_name: str) -> set:
    from .utils import json_read

    ack_file = f"{data_dir}/inbox/{agent_name}/ack.json"
    ack_data = json_read(ack_file, [])
    if isinstance(ack_data, dict):
        ack_data = [ack_data]
    return {
        a.get("msg_id")
        for a in ack_data
        if isinstance(a, dict) and a.get("action") == "ack" and a.get("msg_id")
    }


def verify_pipeline_step_delivery(
    data_dir: str, agent_name: str, msg_entry: dict,
) -> tuple[bool, str]:
    """CLI 结束后验收：msg-results 须存在且 agent/step 匹配当前 chain。"""
    from lib.adapters.orchestration.task_fsm import get_active_step, read_step_result, result_applies_to_step

    content = msg_entry.get("content", "") if isinstance(msg_entry, dict) else ""
    tid = msg_entry.get("task_id") or extract_task_id(content or "")
    if not tid:
        return True, "not_pipeline"
    t = get_running_pipeline_task(data_dir, tid)
    if not t:
        return True, "task_not_running"
    step = get_active_step(t) or (t.get("chain") or [])[-1]
    sa = step.get("to_agent") or step.get("to_person")
    if sa != agent_name or step.get("status") != "running":
        return True, "not_current_step"
    result = read_step_result(data_dir, tid, step)
    if not result:
        return False, "missing_msg_results"
    ok, reason = result_applies_to_step(result, tid, step, t.get("chain") or [])
    if not ok:
        if reason == "stale_prior_step":
            return False, "missing_msg_results"
        return False, reason
    return True, "ok"


def pipeline_repush_cooldown_minutes(config: dict, *, is_primary: bool) -> float:
    ops = config.get("pipeline_ops") or {}
    if is_primary:
        return float(ops.get("primary_repush_cooldown_minutes", 6))
    return float(ops.get("repush_cooldown_minutes", 8))
