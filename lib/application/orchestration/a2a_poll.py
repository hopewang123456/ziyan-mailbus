"""scanner 轮询 A2A 在途 step + input-required 超时。"""
from __future__ import annotations

from lib.infra.clock import now_dt, now_ts, now_utc_dt
import os
from datetime import datetime, timezone
from typing import Any

from lib.composition import get_fsm, get_human_gate, human_queue_path
from .tracker import TaskTracker, _parse_iso_dt
from lib.domain.fsm import TaskFsmState
from lib.core.a2a.config import load_transport_config
from lib.core.a2a.dispatch_integration import build_router, merge_agent_transport_config, transport_router_enabled
from lib.core.a2a.fallback_log import log_input_required_timeout
from lib.core.a2a.step_result_io import write_step_result_file
from lib.core.a2a.types import DispatchContext
from lib.infra.utils import file_lock, json_read, json_write


def poll_pending_a2a_tasks(data_dir: str, agents: dict, paths: dict) -> int:
    """扫描 chain 中带 a2a_task_id 且无 step-result 的步，GetTask 更新。"""
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    if not transport_router_enabled(cfg):
        return 0
    tasks_dir = os.path.join(data_dir, "tasks")
    if not os.path.isdir(tasks_dir):
        return 0
    router = build_router(data_dir, cfg)
    agents = merge_agent_transport_config(agents or cfg.get("agents") or {})
    updated = 0
    hq = get_human_gate(data_dir)
    for name in os.listdir(tasks_dir):
        if not name.endswith(".json"):
            continue
        task = json_read(os.path.join(tasks_dir, name), {})
        task_id = task.get("task_id") or name[:-5]
        for step in task.get("chain") or []:
            if not isinstance(step, dict):
                continue
            a2a_id = step.get("a2a_task_id")
            step_id = step.get("step_id")
            if not a2a_id or not step_id:
                continue
            if step.get("transport_used") != "a2a_standard":
                continue
            from lib.application.orchestration.pipeline.results import step_result_path

            if os.path.isfile(get_fsm().step_result_path(data_dir, task_id, step_id)):
                continue
            to_agent = step.get("to_agent") or step.get("to_person") or ""
            role_type = int(step.get("role_type") or 0)
            ctx = DispatchContext(
                data_dir=data_dir,
                task_id=task_id,
                step_id=step_id,
                to_agent=to_agent,
                role_type=role_type,
            )
            outcome = router.a2a.poll_task(ctx, a2a_id, agents=agents)
            if outcome.get("awaiting_human"):
                hq_item = dict(outcome.get("human_queue") or {})
                hq_item.setdefault("task_id", task_id)
                hq.enqueue(hq_item)
                updated += 1
                continue
            if outcome.get("ok") and outcome.get("step_result"):
                write_step_result_file(
                    data_dir, task_id, step_id, outcome["step_result"],
                    agent=to_agent, role_type=role_type,
                )
                updated += 1
    if updated:
        from lib.application.orchestration.pipeline.trigger import trigger

        trigger(data_dir, agents, paths)
    return updated


def check_input_required_timeouts(data_dir: str, agents: dict, paths: dict) -> int:
    """超过 input_required_timeout_sec 未 resolve → blocked + errors jsonl。"""
    cfg = load_transport_config(None, data_dir=data_dir)
    timeout_sec = int((cfg.get("a2a") or {}).get("input_required_timeout_sec") or 86400)
    if timeout_sec <= 0:
        return 0

    now = now_utc_dt()
    handled = 0
    tra = TaskTracker(data_dir)
    hq = get_human_gate(data_dir)

    lock = file_lock(path=human_queue_path(data_dir))
    with lock:
        items = [
            i for i in hq.load_queue().get("items") or []
            if i.get("status") == "pending"
            and i.get("type") in ("a2a_input_required", "final_acceptance")
        ]
        for item in items:
            created = _parse_iso_dt(item.get("created_at") or "")
            if not created:
                continue
            age = (now - created.astimezone(timezone.utc)).total_seconds()
            if age < timeout_sec:
                continue
            task_id = item.get("task_id") or ""
            if not task_id:
                continue
            task = tra.get(task_id)
            if not task:
                continue
            get_fsm().ensure(task)
            task["fsm"]["state"] = TaskFsmState.BLOCKED.value
            task["status"] = "running"
            task["error"] = f"input_required_timeout:{item.get('type')}"
            json_write(tra._task_path(task_id), task)
            log_input_required_timeout(
                data_dir,
                task_id=task_id,
                step_id=(item.get("context") or {}).get("step_id") or "",
                hq_id=item.get("id") or "",
                hq_type=item.get("type") or "",
                age_sec=int(age),
            )
            _notify_notify_agent(data_dir, paths, task_id, item, age_sec=int(age))
            handled += 1
    return handled


def _notify_notify_agent(data_dir: str, paths: dict, task_id: str, item: dict, *, age_sec: int) -> None:
    try:
        from lib.infra.org_defaults import org_default
        from lib.domain.models import Inbox
        from lib.infra.utils import json_read, _now_iso

        notify_agent = org_default(data_dir, "notify_agent")
        inbox_path = os.path.join(paths["inbox"], notify_agent, "inbox.json")
        inbox = Inbox.from_dict(json_read(inbox_path, {})) if os.path.isfile(inbox_path) else Inbox(agent=notify_agent)
        inbox.messages.append({
            "id": f"hq-timeout-{item.get('id', task_id)}",
            "from": "mailbus",
            "to": notify_agent,
            "type": "notice",
            "priority": "high",
            "state": "pending",
            "task_id": task_id,
            "content": (
                f"⚠️ HQ 超时 {item.get('type')} task={task_id} "
                f"hq={item.get('id')} age={age_sec // 3600}h"
            ),
            "created_at": _now_iso(),
        })
        inbox.has_unread = True
        json_write(inbox_path, inbox.to_dict())
    except OSError:
        pass
