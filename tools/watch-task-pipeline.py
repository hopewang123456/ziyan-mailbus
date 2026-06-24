#!/usr/bin/env python3
"""单任务 pipeline 实时监控 — 12 步全员链、inbox、msg-results、卡点检测。

用法:
  python3 tools/watch-task-pipeline.py --task-id game-stellar-20260616
  python3 tools/watch-task-pipeline.py --task-id game-stellar-20260616 --interval 30 --rounds 120
  python3 tools/watch-task-pipeline.py --task-id game-stellar-20260616 --no-scan
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.pipeline_chain import agent_to_role
from lib.tracker import TaskTracker
from lib.utils import json_read

TZ = timezone(timedelta(hours=8))
LOG_DIR = "/tmp"


def _now() -> str:
    return datetime.now(TZ).strftime("%H:%M:%S")


def _log(msg: str, log_path: str) -> None:
    line = f"[{_now()}] {msg}"
    print(line, flush=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _inbox_state(data_dir: str, agent: str, task_id: str) -> dict:
    p = os.path.join(data_dir, "inbox", agent, "inbox.json")
    data = json_read(p, {})
    hits = []
    for m in data.get("messages") or []:
        content = m.get("content") or ""
        if task_id in content or m.get("task_id") == task_id:
            hits.append({
                "id": m.get("id"),
                "state": m.get("state"),
                "status": m.get("status"),
                "pushed_count": m.get("pushed_count", 0),
                "priority": m.get("priority"),
            })
    return {"has_unread": data.get("has_unread"), "hits": hits}


def _msg_result(data_dir: str, task_id: str) -> dict | None:
    p = os.path.join(data_dir, "msg-results", f"{task_id}.json")
    if not os.path.isfile(p):
        return None
    r = json_read(p, {})
    return {
        "conclusion": r.get("conclusion"),
        "agent": r.get("agent"),
        "pipeline_step": r.get("pipeline_step"),
        "next_role": r.get("next_role"),
        "next_person": r.get("next_person"),
        "summary": (r.get("summary") or "")[:80],
        "mtime": datetime.fromtimestamp(os.path.getmtime(p), TZ).strftime("%H:%M:%S"),
    }


def _planned_queue(task: dict) -> list:
    chain = task.get("chain") or []
    if not chain:
        return []
    head = chain[0]
    if head.get("planned_role_types"):
        return list(head["planned_role_types"])
    return list(head.get("planned_agents") or [])


def _build_step_matrix(task: dict, planned_full: list[str]) -> list[dict]:
    """已完成 chain 步骤 + planned 剩余 = 全景矩阵。"""
    chain = task.get("chain") or []
    rows = []
    for i, s in enumerate(chain):
        if not isinstance(s, dict):
            continue
        rows.append({
            "n": i + 1,
            "person": s.get("to_person", "?"),
            "role": s.get("to_role", "?"),
            "status": s.get("status", "?"),
            "phase": "done" if s.get("status") in ("completed", "done") else "active",
        })
    start_n = len(rows) + 1
    for j, person in enumerate(planned_full):
        rows.append({
            "n": start_n + j,
            "person": person,
            "role": agent_to_role(person),
            "status": "pending",
            "phase": "planned",
        })
    return rows


def _detect_issues(task: dict, result: dict | None, cur_person: str, stall_rounds: int) -> list[str]:
    issues = []
    status = task.get("status", "")
    chain = task.get("chain") or []
    cur = chain[-1] if chain else {}

    if status in ("success", "failed", "cancelled", "timeout"):
        return issues

    if stall_rounds >= 3:
        issues.append(f"STALL step={cur.get('step')} {cur_person} 已 {stall_rounds} 轮无推进")

    if result:
        step = cur.get("step") or len(chain)
        r_step = result.get("pipeline_step")
        if r_step is not None and int(r_step) != int(step):
            issues.append(f"RESULT step 不匹配: file={r_step} chain={step}")
        r_agent = result.get("agent")
        if r_agent and r_agent != cur_person:
            issues.append(f"RESULT agent 不匹配: file={r_agent} expect={cur_person}")

    if cur.get("status") == "running" and result and result.get("conclusion"):
        issues.append("RESULT 已写但 chain 未推进 — 可能 trigger/scan 未跑或校验失败")

    return issues


def _run_scan(mail_root: str) -> None:
    try:
        subprocess.Popen(
            ["flock", "-n", "/tmp/mailbus-scan.lock", "python3", "-m", "bus", "scan", "--data-dir", "store"],
            cwd=mail_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def one_round(
    data_dir: str,
    task_id: str,
    mail_root: str,
    log_path: str,
    *,
    do_scan: bool,
    last_signature: str,
    stall_rounds: int,
) -> tuple[str, int, bool]:
    tr = TaskTracker(data_dir)
    task = tr.get(task_id)
    if not task:
        _log(f"ERROR 任务不存在: {task_id}", log_path)
        return last_signature, stall_rounds, True

    chain = task.get("chain") or []
    cur = chain[-1] if chain else {}
    cur_person = cur.get("to_person") or task.get("assignee") or "?"
    planned = _planned_queue(task)
    planned_full = planned  # 剩余队列
    matrix = _build_step_matrix(task, planned_full)
    result = _msg_result(data_dir, task_id)
    inbox = _inbox_state(data_dir, cur_person, task_id) if cur_person != "?" else {}

    signature = (
        f"{task.get('status')}|{len(chain)}|{cur_person}|{cur.get('status')}|"
        f"{result.get('pipeline_step') if result else '-'}|{len(planned)}"
    )

    terminal = task.get("status") in ("success", "failed", "cancelled", "timeout")

    if signature != last_signature:
        stall_rounds = 0
        _log(f"── 变化检测 task={task_id} ──", log_path)
        _log(
            f"  状态={task.get('status')} step={cur.get('step', len(chain))}/12 "
            f"当前={cur.get('to_role')}/{cur_person} ({cur.get('status')})",
            log_path,
        )
        _log(f"  planned 剩余 ({len(planned)}): {' → '.join(planned[:6])}{'…' if len(planned) > 6 else ''}", log_path)
        if result:
            _log(
                f"  msg-results: step={result.get('pipeline_step')} agent={result.get('agent')} "
                f"conclusion={result.get('conclusion')} mtime={result.get('mtime')}",
                log_path,
            )
        if inbox.get("hits"):
            h = inbox["hits"][-1]
            _log(
                f"  inbox[{cur_person}]: state={h.get('state')} pushed={h.get('pushed_count')} id={h.get('id')}",
                log_path,
            )
        done_n = sum(1 for r in matrix if r["phase"] == "done")
        _log(f"  进度: {done_n} 完成 / {len(matrix)} 总步（含 planned）", log_path)
    else:
        stall_rounds += 1

    issues = _detect_issues(task, result, cur_person, stall_rounds)
    for iss in issues:
        _log(f"  ⚠ {iss}", log_path)

    if do_scan and not terminal:
        if stall_rounds >= 2 or (signature != last_signature and stall_rounds == 0 and result):
            _run_scan(mail_root)
            _log("  → 已异步触发 bus scan", log_path)

    return signature, stall_rounds, terminal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--data-dir", default=os.environ.get("MAILBUS_DATA", "store"))
    ap.add_argument("--interval", type=int, default=30, help="轮询间隔秒")
    ap.add_argument("--rounds", type=int, default=9999)
    ap.add_argument("--no-scan", action="store_true", help="不自动触发 scan")
    args = ap.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    mail_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_path = os.path.join(LOG_DIR, f"pipeline-watch-{args.task_id}.log")

    _log(f"WATCH START task={args.task_id} interval={args.interval}s log={log_path}", log_path)

    last_sig = ""
    stall = 0
    for r in range(1, args.rounds + 1):
        _log(f"--- round {r} ---", log_path)
        last_sig, stall, terminal = one_round(
            data_dir, args.task_id, mail_root, log_path,
            do_scan=not args.no_scan,
            last_signature=last_sig,
            stall_rounds=stall,
        )
        if terminal:
            _log(f"TASK TERMINAL status reached — watch 结束", log_path)
            break
        if r < args.rounds:
            time.sleep(args.interval)

    _log("WATCH END", log_path)


if __name__ == "__main__":
    main()
