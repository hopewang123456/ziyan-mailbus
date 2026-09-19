"""Wave 2 E-demo — 零依赖演示链：type=none 纯文件通信 + 预设回复脚本。

一条命令看到第一条工单完整流转（建单 → 派工 → 投递 → 执行 → 回执 → 归档）：
- 演示数据独立命名空间 ``<data_dir>/demo/``，一键清除，不污染真实 store；
- 不装任何框架、不配任何 key（demo 角色 type=none，脚本化应答）；
- 流转叙事落 ``demo/trace.json``，驾驶舱/后续向导可直接取材。
"""
from __future__ import annotations

import os
import shutil
import time
from typing import Any, Callable

from lib.infra.clock import now_ts
from lib.infra.utils import _now_iso, json_read, json_write, resolve_paths

DEMO_NAMESPACE = "demo"

# 演示员工（type=none 纯文件通信；reply 为预设回执脚本）
DEMO_AGENTS: dict[str, dict[str, Any]] = {
    "demo-dev": {
        "name": "小开",
        "role": "开发工程师",
        "conclusion": "done",
        "summary": "已按工单完成实现（demo 预设回复，零 LLM 消耗）",
    },
    "demo-check": {
        "name": "小校",
        "role": "质检员",
        "conclusion": "pass",
        "summary": "复核通过：产物与验收口径一致（demo 预设回复）",
    },
    "demo-notify": {
        "name": "小鸣",
        "role": "通知员",
        "conclusion": "done",
        "summary": "结论通知已发出（demo 预设回复）",
    },
}

# demo 角色 → role_type 候选（与正式模板语义对齐：8=开发 5=质检 7=巡检）
DEMO_ROLE_TYPES = {
    "8": {"key": "developer", "display": {"zh": "开发工程师", "en": "Developer"}, "candidates": ["demo-dev"]},
    "5": {"key": "reviewer", "display": {"zh": "质检员", "en": "Reviewer"}, "candidates": ["demo-check"]},
    "7": {"key": "ops_patrol", "display": {"zh": "巡检官", "en": "Ops Patrol"}, "candidates": ["demo-notify"]},
}


def demo_dir(data_dir: str) -> str:
    return os.path.join(data_dir, DEMO_NAMESPACE)


def clean_demo(data_dir: str) -> bool:
    d = demo_dir(data_dir)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
        return True
    return False


def ensure_demo_store(data_dir: str) -> str:
    """建演示命名空间（幂等）：config + role-types + 目录树。"""
    d = demo_dir(data_dir)
    os.makedirs(os.path.join(d, "roles", "json"), exist_ok=True)
    for sub in ("inbox", "tasks", "msg-results", "msg-files", "dispatch", "errors", "replies", "ledger"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    for aid, meta in DEMO_AGENTS.items():
        os.makedirs(os.path.join(d, "inbox", aid), exist_ok=True)

    cfg_path = os.path.join(d, "config.json")
    cfg = json_read(cfg_path, {})
    cfg.setdefault("agents", {}).update({
        aid: {"name": meta["name"], "role": meta["role"], "type": "none", "enabled": True}
        for aid, meta in DEMO_AGENTS.items()
    })
    cfg.setdefault("transport", {})["use_router"] = True
    cfg.setdefault("harness", {})["mode"] = "production"
    json_write(cfg_path, cfg)

    rt_path = os.path.join(d, "roles", "json", "role-types.json")
    rt = json_read(rt_path, {"version": "1.0.0", "roles": {}})
    rt["roles"].update(DEMO_ROLE_TYPES)
    json_write(rt_path, rt)
    return d


def _demo_tick(demo_d: str, trace: list[dict[str, Any]]) -> int:
    """脚本化执行器：替每个 demo 角色消费 inbox 工单（写 ack + 预设 step-result）。"""
    from lib.core.a2a.step_result_io import write_step_result_file

    acted = 0
    for aid, meta in DEMO_AGENTS.items():
        inbox_path = os.path.join(demo_d, "inbox", aid, "inbox.json")
        inbox = json_read(inbox_path, {"agent": aid, "messages": []})
        acks = json_read(os.path.join(demo_d, "inbox", aid, "ack.json"), [])
        acked_ids = {a.get("msg_id") for a in acks if isinstance(a, dict)}
        for m in inbox.get("messages") or []:
            mid = m.get("id") or ""
            if not mid or mid in acked_ids or m.get("type") not in ("task", "task_reply"):
                continue
            task_id = str(m.get("task_id") or "")
            step_id = str(m.get("step_id") or "")
            if not (task_id and step_id):
                continue
            acks.append({"action": "ack", "msg_id": mid, "agent": aid, "timestamp": _now_iso()})
            trace.append({"event": "ack", "agent": aid, "msg_id": mid, "ts": _now_iso()})
            write_step_result_file(
                demo_d, task_id, step_id,
                {"status": "completed", "conclusion": meta["conclusion"],
                 "summary": meta["summary"], "agent": aid},
                agent=aid,
            )
            trace.append({"event": "step_result", "agent": aid, "task_id": task_id,
                          "step_id": step_id, "conclusion": meta["conclusion"], "ts": _now_iso()})
            acted += 1
        if acks:
            json_write(os.path.join(demo_d, "inbox", aid, "ack.json"), acks)
    return acted


def run_demo(
    data_dir: str,
    *,
    intent: str = "演示：整理目录并输出清单",
    on_event: Callable[[str], None] | None = None,
    max_rounds: int = 12,
) -> dict[str, Any]:
    """跑一条两步演示工单（开发 → 质检）直到终态，返回叙事 trace。

    on_event：每步流转的回调（CLI 打印 / 测试断言用）。
    """
    def say(line: str) -> None:
        trace_events.append({"event": "narrative", "line": line, "ts": _now_iso()})
        if on_event:
            on_event(line)

    demo_d = ensure_demo_store(data_dir)
    trace_events: list[dict[str, Any]] = []

    task_id = f"demo-{int(now_ts())}"
    envelope = {
        "task_id": task_id,
        "intent": intent,
        "initiator": "demo",
        "mode": "explicit",
        "tier": "S",
        "task_type": "demo",
        "planned_chain": [
            {"role_type": 8, "reason": "执行"},
            {"role_type": 5, "reason": "复核"},
        ],
    }

    from lib.application.orchestration.router.envelope_validate import validate_envelope
    from lib.application.orchestration.router.planner import plan_tier0
    from lib.application.orchestration.tracker import TaskTracker
    from lib.application.workflow.engine import bind_workflow
    from lib.application.orchestration.router.dispatch import dispatch_first_step, start_executing

    errors = validate_envelope(envelope, data_dir=demo_d)
    if errors:
        return {"ok": False, "error": f"envelope invalid: {errors}"}
    out = plan_tier0(envelope, data_dir=demo_d)
    planned, plan_meta = out["planned_chain"], out["plan_meta"]

    tracker = TaskTracker(demo_d)
    task = tracker.create_from_envelope(envelope, planned_chain=planned, plan_meta=plan_meta)
    bind_workflow(task, envelope, data_dir=demo_d)
    json_write(tracker._task_path(task_id), task)
    start_executing(task)
    from lib.infra.role_types import role_type_to_zh

    say(f"① 建单 {task_id}：{intent}")
    say("   规划链: " + " → ".join(role_type_to_zh(int(s.get("role_type") or 0), demo_d) for s in planned))
    if not dispatch_first_step(demo_d, task):
        say("✗ 首步派发失败（demo store 配置异常）")
        return {"ok": False, "error": "dispatch_failed", "trace": trace_events}
    first = (planned[0].get("to_agent") or task.get("assignee") or "?")
    say(f"② 派工 → {first}（工单消息已投递 inbox）")

    from lib.application.orchestration.pipeline.trigger import trigger

    agents = json_read(os.path.join(demo_d, "config.json"), {}).get("agents") or {}
    paths = resolve_paths(demo_d)
    final_status = "unknown"
    for round_n in range(1, max_rounds + 1):
        acted = _demo_tick(demo_d, trace_events)
        if acted:
            say(f"③ 执行+回执：demo 角色消费工单并写 step-result（{acted} 条）")
        trigger(demo_d, agents, paths)
        t = tracker.get(task_id) or {}
        status = t.get("status") or ""
        if status != final_status and status in ("success", "blocked", "failed", "cancelled"):
            final_status = status
        if status in ("success", "blocked", "failed", "cancelled"):
            break
        # 全步骤完成 → accepting：demo 发起人模拟验收（完整闭环的最后一环）
        if (t.get("fsm") or {}).get("state") == "accepting" and not (t.get("acceptance_record") or {}):
            from lib.application.orchestration.actions import apply_accept

            task = tracker.get(task_id) or {}
            outcome = apply_accept(
                task,
                {"decision": "approved", "reviewer": "demo-initiator", "comment": "demo 验收通过"},
                data_dir=demo_d,
            )
            if outcome.get("ok"):
                json_write(tracker._task_path(task_id), task)  # apply_accept 只改内存，落盘归调用方
                say("④ 验收：发起人确认验收（approved）")
            time.sleep(0.1)
            continue
        time.sleep(0.2)

    t = tracker.get(task_id) or {}
    final_status = t.get("status") or final_status
    if final_status == "success":
        say("⑤ 归档：工单 success —— 完整闭环 ✓（建单→派工→投递→执行→回执→验收→归档，全程零 LLM、零框架依赖）")
    else:
        say(f"✗ 工单终态 {final_status}（demo 链异常，查 {demo_d}/tasks/{task_id}.json）")

    json_write(os.path.join(demo_d, "trace.json"), {"task_id": task_id, "events": trace_events})
    return {
        "ok": final_status == "success",
        "task_id": task_id,
        "status": final_status,
        "steps": [
            {"step_id": s.get("step_id"), "to_agent": s.get("to_agent"),
             "fsm_state": s.get("fsm_state"), "status": s.get("status")}
            for s in (t.get("chain") or [])
        ],
        "demo_dir": demo_d,
        "trace": trace_events,
    }
