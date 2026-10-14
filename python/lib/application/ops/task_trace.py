"""Wave 5 E9 — 消息生命周期 trace：发起→派工→投递→执行→回执→验收→归档，可回放。

聚合三路时间戳为单一时序（每步带 ts）：
- task.json 本体：created_at / events / chain 步骤 started_at·completed_at /
  transport_attempts / acceptance_record / status / updated_at；
- msg-results/<task>/step-*.json：agent 回执落盘时刻（执行完成的权威时间）；
- ledger tokens-*.jsonl（E3）：push / result_usage 记账时刻（token 佐证）。

phase 词表：created / planned / dispatched / delivered / ack_receipt /
step_done / advance / accepted / terminal / blocked / note。
"""
from __future__ import annotations

import json
import os
from typing import Any

from lib.infra.utils import json_read

_PHASE_ORDER = {
    "created": 0, "planned": 1, "dispatched": 2, "delivered": 3,
    "ack_receipt": 4, "step_done": 5, "advance": 6, "accepted": 7,
    "terminal": 8, "blocked": 8, "note": 9,
}


def _add(events: list[dict[str, Any]], ts: str, phase: str, actor: str, detail: str, source: str) -> None:
    if not ts:
        return
    events.append({"ts": str(ts)[:19], "phase": phase, "actor": actor,
                   "detail": detail, "source": source})


def _step_result_ts(data_dir: str, task_id: str, step_id: str) -> str:
    from lib.infra.pipeline_results import step_result_path

    p = step_result_path(data_dir, task_id, step_id)
    if not os.path.isfile(p):
        return ""
    doc = json_read(p, {})
    return str(doc.get("timestamp") or "")


def _inbox_delivered_at(data_dir: str, agents: set[str], task_id: str) -> str:
    best = ""
    for agent in agents:
        p = os.path.join(data_dir, "inbox", agent, "inbox.json")
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                inbox = json.load(f)
        except json.JSONDecodeError:
            continue
        for m in inbox.get("messages") or []:
            if str(m.get("task_id") or "") == task_id:
                ts = str(m.get("created_at") or "")
                if ts and (not best or ts < best):
                    best = ts
    return best


def task_trace(data_dir: str, task_id: str) -> dict[str, Any]:
    task_path = os.path.join(data_dir, "tasks", f"{task_id}.json")
    task = json_read(task_path, {})
    if not task:
        raise ValueError(f"unknown task: {task_id}")

    events: list[dict[str, Any]] = []
    _add(events, task.get("created_at"), "created",
         str(task.get("initiator") or "human"), f"建单：{(task.get('intent') or '')[:60]}", "task")

    # planner 痕迹（plan_meta）+ 任务事件流
    pm = task.get("plan_meta") or {}
    if pm:
        _add(events, task.get("created_at"), "planned", "planner",
             f"规划方法 {pm.get('method')} · {len(task.get('chain') or [])} 步", "task.plan_meta")
    for e in task.get("events") or []:
        if not isinstance(e, dict):
            continue
        action = str(e.get("action") or "")
        phase = "note"
        for kw, ph in (("dispatch", "dispatched"), ("accept", "accepted"),
                       ("blocked", "blocked"), ("verify", "note")):
            if kw in action:
                phase = ph
                break
        _add(events, e.get("ts"), phase, str(e.get("actor") or "system"),
             f"{action}{' · ' + str(e.get('note') or '')[:60] if e.get('note') else ''}", "task.events")

    # 步骤生命周期
    chain_agents: set[str] = set()
    for s in task.get("chain") or []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("step_id") or "")
        agent = str(s.get("to_agent") or s.get("to_person") or "")
        station = str(s.get("station") or "")
        who = f"{station or ''}{'→' if station and agent else ''}{agent}".strip("→") or "?"
        if agent:
            chain_agents.add(agent)
        _add(events, s.get("started_at"), "dispatched", who,
             f"步骤 {sid} 派工{'（工位 ' + station + '）' if station else ''}", "task.chain")

        # transport 尝试（a2a 重试/fallback 时间戳）
        for att in s.get("transport_attempts") or []:
            if isinstance(att, dict) and att.get("ts"):
                _add(events, att["ts"], "delivered", who,
                     f"投递通道 {att.get('channel')} · {att.get('outcome')}", "step.transport_attempts")

        ts_result = _step_result_ts(data_dir, task_id, sid)
        if ts_result:
            _add(events, ts_result, "step_done", agent,
                 f"步骤 {sid} 回执（{s.get('fsm_state') or s.get('status')}）", "msg-results")
        _add(events, s.get("completed_at"), "step_done", agent,
             f"步骤 {sid} 完成", "task.chain")

    delivered = _inbox_delivered_at(data_dir, chain_agents, task_id)
    _add(events, delivered, "delivered", "file_bus", "工单消息落 inbox", "inbox")

    # E3 台账（token 佐证：每次 push / 回执 usage）
    try:
        from lib.infra.token_ledger import by_task

        for le in by_task(data_dir, task_id, limit=100):
            phase = "dispatched" if le.get("kind") == "push" else "step_done"
            _add(events, le.get("ts"), phase, str(le.get("agent") or ""),
                 f"台账 {le.get('kind')} · {le.get('est_tokens')} tok（{le.get('source')}）", "ledger")
    except Exception:
        pass

    acc = task.get("acceptance_record") or {}
    if acc:
        _add(events, acc.get("resolved_at") or acc.get("ts"), "accepted",
             str(acc.get("reviewer") or ""), f"验收 {acc.get('decision')}（{acc.get('method')}）", "acceptance")

    status = str(task.get("status") or "")
    phase = "terminal" if status in ("success", "cancelled") else ("blocked" if status == "blocked" else "note")
    _add(events, task.get("updated_at"), phase, "system",
         f"当前状态 {status}" + (f" · {(task.get('fsm') or {}).get('reason')}" if status == "blocked" else ""),
         "task.status")

    # 稳定排序：ts 升序，同刻按生命周期阶段
    events.sort(key=lambda e: (e["ts"], _PHASE_ORDER.get(e["phase"], 9)))
    return {
        "task_id": task_id,
        "status": status,
        "intent": (task.get("intent") or "")[:120],
        "steps": [
            {"step_id": s.get("step_id"), "station": s.get("station", ""),
             "to_agent": s.get("to_agent"), "fsm_state": s.get("fsm_state")}
            for s in (task.get("chain") or []) if isinstance(s, dict)
        ],
        "events": events,
        "event_count": len(events),
    }


def format_trace_text(trace: dict[str, Any]) -> str:
    lines = [
        f"工单回放: {trace['task_id']}（{trace['status']}）",
        f"  意图: {trace['intent']}",
        f"  步骤: " + " → ".join(
            f"{s.get('step_id')}:{s.get('station') or s.get('to_agent') or '?'}"
            for s in trace.get("steps") or []
        ),
        "时序:",
    ]
    for e in trace.get("events") or []:
        lines.append(
            f"  [{e['ts']}] {e['phase']:<10} {e['actor']:<12} {e['detail']}"
        )
    return "\n".join(lines)
