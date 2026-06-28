"""mailbus 三轮迭代引擎 — 每轮输出作为下一轮输入。

Round 1: 现象 → 结构化问题清单 (diagnosis.json)
Round 2: 问题清单 → 可执行工单 (backlog.json)
Round 3: 工单 → 自迭代协议 + 下一轮 Round1 触发条件 (protocol.json)

由 `bus iteration` 或 scan housekeeping 调用。
"""

from __future__ import annotations

import glob
import os
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .constants import MAILBUS_ROOT
from .utils import json_read, json_write, resolve_paths, _now_iso
from .tracker import TaskTracker, TaskStatus
from .pipeline_chain import is_pipeline_step

TZ = timezone(timedelta(hours=8))
ITER_DIR = "iterations"
STATE_FILE = "iteration-state.json"
DEFAULT_PRIMARY_TASK = "mailbus-scheduler-validation-20260616"


def load_primary_task_id(data_dir: str) -> str:
    """从 iteration-state 读取主任务 ID，缺省用 DEFAULT_PRIMARY_TASK。"""
    st = json_read(_state_path(data_dir), None)
    if st and st.get("primary_task_id"):
        return st["primary_task_id"]
    return DEFAULT_PRIMARY_TASK

# 系统噪音 task 前缀 — 不计入「业务任务健康度」
NOISE_PREFIXES = (
    "remind-", "tracker-remind-", "patrol-", "heartbeat-",
    "confirm-", "rule-change-", "alert-task-",
)

TERMINAL_MSG = frozenset({"done", "closed", "rejected", "failed", "archived", "sent"})
ACTIVE_MSG = frozenset({"processing", "acknowledged", "pushed", "running", "in_progress"})


def _state_path(data_dir: str) -> str:
    return _iter_path(data_dir, STATE_FILE)


def load_iteration_state(data_dir: str) -> dict:
    default = {
        "primary_task_id": DEFAULT_PRIMARY_TASK,
        "round1": {"phase": "execution", "status": "running"},
        "round2_unlocked": False,
        "round3_unlocked": False,
        "note": "Round2 仅在 Round1 主任务 success + 灵鉴 audit pass 后解锁",
    }
    st = json_read(_state_path(data_dir), None)
    return st if st else default


def save_iteration_state(data_dir: str, state: dict) -> dict:
    state["updated_at"] = _now_iso()
    json_write(_state_path(data_dir), state)
    return state


def evaluate_round1_gate(data_dir: str, agents: dict = None) -> dict:
    """Round1 门禁：主任务 success + 灵鉴 audit pass/warn → 才允许 Round2。"""
    from .audit_dispatch import list_pending_audit_tasks

    tracker = TaskTracker(data_dir)
    primary = load_primary_task_id(data_dir)
    state = load_iteration_state(data_dir)
    task = tracker.get(primary)
    pending = list_pending_audit_tasks(data_dir, 500)

    result = {
        "primary_task_id": primary,
        "primary_status": task.get("status") if task else "missing",
        "primary_has_audit": bool(task and task.get("audit_log")),
        "primary_audit_result": None,
        "pending_audit_total": len(pending),
        "pending_audit_primary": primary in [t["task_id"] for t in pending],
        "round1_passed": False,
        "round2_unlocked": False,
        "blockers": [],
    }

    if task and task.get("audit_log"):
        last = task["audit_log"][-1]
        if isinstance(last, dict):
            result["primary_audit_result"] = last.get("result")

    if not task:
        result["blockers"].append(f"主任务 {primary} 不存在")
    elif task.get("status") != TaskStatus.SUCCESS:
        result["blockers"].append(
            f"主任务须 status=success（当前 {task.get('status')}），请先完成 pipeline 执行"
        )

    if not task or not task.get("audit_log"):
        result["blockers"].append("主任务须由灵鉴写入 audit_log（POST /api/tasks/audit 或 msg-results/audit-*.json）")
    elif result["primary_audit_result"] == "fail":
        result["blockers"].append("主任务审计 result=fail，需修复后重新审计")

    if not result["blockers"]:
        result["round1_passed"] = True
        result["round2_unlocked"] = True

    if task:
        if result["round1_passed"]:
            state["round1"]["status"] = "passed"
        elif task.get("status") in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT):
            state["round1"]["status"] = "awaiting_audit"
        else:
            state["round1"]["status"] = "execution"
    state["round2_unlocked"] = result["round2_unlocked"]
    state["gate"] = result
    save_iteration_state(data_dir, state)
    json_write(_iter_path(data_dir, "round-1-gate.json"), result)
    return result


def _iter_path(data_dir: str, name: str) -> str:
    d = os.path.join(data_dir, ITER_DIR)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _is_noise_task(task_id: str, summary: str = "") -> bool:
    if any(task_id.startswith(p) for p in NOISE_PREFIXES):
        return True
    s = (summary or "")[:60]
    return s.startswith("⚠️ 超时提醒") or s.startswith("⏰ 催办提醒")


def _inbox_stats(data_dir: str, agents: dict) -> Dict[str, dict]:
    paths = resolve_paths(data_dir)
    stats = {}
    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        data = json_read(inbox_file, {})
        if isinstance(data, list):
            msgs = data
        elif isinstance(data, dict):
            msgs = data.get("messages", [])
        else:
            msgs = []
        pending = active = done = task_pending = 0
        for m in msgs:
            if not isinstance(m, dict):
                continue
            state = (m.get("state") or m.get("status") or "").lower()
            mtype = (m.get("type") or "").lower()
            if state in TERMINAL_MSG:
                done += 1
            elif state in ACTIVE_MSG:
                active += 1
            else:
                pending += 1
            if mtype in ("task", "task_reply") and state not in TERMINAL_MSG:
                task_pending += 1
        stats[name] = {
            "total": len(msgs),
            "pending": pending,
            "active": active,
            "done": done,
            "task_pending": task_pending,
        }
    return stats


def _task_stats(data_dir: str) -> dict:
    tracker = TaskTracker(data_dir)
    all_tasks = tracker.list_all()
    by_status = Counter()
    pipeline_running = []
    pipeline_timeout = []
    false_timeout = []

    bracket_re = re.compile(r"【([^】]{4,120})】")
    task_states = _build_task_inbox_index(data_dir, {})

    for t in all_tasks:
        tid = t.get("task_id", "")
        if _is_noise_task(tid, t.get("summary", "")):
            continue
        st = t.get("status", "?")
        by_status[st] += 1
        chain = t.get("chain") or []
        is_pipe = bool(chain and isinstance(chain[0], dict) and (
            is_pipeline_step(chain[0]) or chain[0].get("planned_agents")))
        if is_pipe and st == TaskStatus.RUNNING:
            pipeline_running.append(tid)
        if is_pipe and st == TaskStatus.TIMEOUT:
            pipeline_timeout.append(tid)
            inbox_st = task_states.get(tid, "")
            if inbox_st in ACTIVE_MSG or inbox_st in ("", "pending", "sent", "new"):
                false_timeout.append(tid)

    return {
        "by_status": dict(by_status),
        "pipeline_running": pipeline_running[:20],
        "pipeline_timeout": pipeline_timeout[:20],
        "false_timeout": false_timeout[:20],
        "total_business": sum(by_status.values()),
    }


def _build_task_inbox_index(data_dir: str, agents: dict) -> Dict[str, str]:
    from .models import Inbox
    paths = resolve_paths(data_dir)
    task_states = {}
    bracket_re = re.compile(r"【([^】]{4,120})】")
    agent_names = agents or {}
    if not agent_names:
        inbox_root = paths["inbox"]
        if os.path.isdir(inbox_root):
            agent_names = {
                d: {} for d in os.listdir(inbox_root)
                if os.path.isdir(os.path.join(inbox_root, d)) and not d.startswith(".")
            }
    for name in agent_names:
        inbox_data = json_read(f"{paths['inbox']}/{name}/inbox.json", {})
        if not inbox_data:
            continue
        if isinstance(inbox_data, list):
            msgs_raw = inbox_data
        else:
            inbox = Inbox.from_dict(inbox_data)
            msgs_raw = inbox.messages
        for m in msgs_raw:
            if isinstance(m, dict):
                mid = m.get("id", "")
                state = (m.get("state") or m.get("status") or "").lower()
                content = m.get("content", "") or ""
                task_id_field = m.get("task_id", "")
            else:
                mid = inbox.msg_field(m, "id", "")
                state = (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")).lower()
                content = inbox.msg_field(m, "content", "")
                task_id_field = inbox.msg_field(m, "task_id", "")
            if not mid:
                continue
            for key in (task_id_field, mid):
                if key:
                    task_states[key] = state
            for match in bracket_re.finditer(content):
                tid = match.group(1).strip()
                if tid:
                    task_states[tid] = state
    return task_states


def _msg_results_count(data_dir: str) -> int:
    d = os.path.join(data_dir, "msg-results")
    if not os.path.isdir(d):
        return 0
    return len(glob.glob(os.path.join(d, "*.json")))


def _recent_cron_errors(data_dir: str, tail: int = 30) -> List[str]:
    log_path = os.path.join(data_dir, "cron.log")
    if not os.path.isfile(log_path):
        return []
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []
    errors = []
    for line in lines[-500:]:
        low = line.lower()
        if any(k in low for k in ("traceback", "error", "exception", "failed", "异常")):
            errors.append(line.strip()[:200])
    return errors[-tail:]


def run_round1(data_dir: str, agents: dict) -> dict:
    """Round 1: 从当前现象生成结构化诊断。"""
    inbox = _inbox_stats(data_dir, agents)
    tasks = _task_stats(data_dir)
    config = json_read(os.path.join(data_dir, "config.json"), {})

    if tasks.get("false_timeout"):
        reopened = TaskTracker(data_dir).reopen_stale_timeouts(agents, data_dir)
        if reopened:
            tasks = _task_stats(data_dir)

    problems = []

    # P1 吞吐瓶颈
    for agent, st in inbox.items():
        if st["task_pending"] >= 5 or st["pending"] >= 50:
            problems.append({
                "id": f"R1-INBOX-{agent}",
                "severity": "critical" if st["pending"] >= 100 else "high",
                "category": "inbox_backlog",
                "agent": agent,
                "symptom": f"{agent} inbox 积压：total={st['total']} pending={st['pending']} task_pending={st['task_pending']}",
                "root_cause_hypothesis": "串行队列 + 历史 notice/reply 未归档 + max_concurrency=1",
                "evidence": st,
            })

    # P2 误 timeout
    if tasks["false_timeout"]:
        problems.append({
            "id": "R1-FALSE-TIMEOUT",
            "severity": "high",
            "category": "tracker_timeout",
            "symptom": f"{len(tasks['false_timeout'])} 个 pipeline 任务误标 timeout（inbox 仍在 pending/processing）",
            "root_cause_hypothesis": "task_id 与 msg_id 不一致 + 催办间隔过短（已部分修复，需 scan 生效）",
            "evidence": {"task_ids": tasks["false_timeout"]},
        })

    # P3 pipeline 卡住
    stuck = []
    for tid in tasks["pipeline_running"]:
        if not os.path.exists(os.path.join(data_dir, "msg-results", f"{tid}.json")):
            stuck.append(tid)
    if stuck:
        problems.append({
            "id": "R1-PIPELINE-STUCK",
            "severity": "critical",
            "category": "pipeline_stuck",
            "symptom": f"{len(stuck)} 个 running pipeline 任务无 msg-results",
            "root_cause_hypothesis": "assignee inbox 未消费 / agent 未写结果文件",
            "evidence": {"task_ids": stuck[:15]},
        })

    # P4 超时任务堆积
    if tasks["by_status"].get("timeout", 0) >= 3:
        problems.append({
            "id": "R1-TIMEOUT-SURGE",
            "severity": "high",
            "category": "tracker_timeout",
            "symptom": f"业务任务 timeout 计数={tasks['by_status'].get('timeout', 0)}",
            "root_cause_hypothesis": "agent 未响应或 inbox 队列过长导致 SLA 耗尽",
            "evidence": {"by_status": tasks["by_status"]},
        })

    # P5 配置/运维
    reminder = config.get("reminder_minutes", 5)
    if reminder < 15:
        problems.append({
            "id": "R1-REMINDER-TOO-AGGRESSIVE",
            "severity": "medium",
            "category": "config",
            "symptom": f"reminder_minutes={reminder} 过短",
            "root_cause_hypothesis": "真实 agent 任务无法在 15 分钟内完成",
            "evidence": {"reminder_minutes": reminder, "max_reminders": config.get("max_reminders")},
        })

    cron_errs = _recent_cron_errors(data_dir)
    if cron_errs:
        problems.append({
            "id": "R1-CRON-ERRORS",
            "severity": "high",
            "category": "ops",
            "symptom": f"cron.log 近期 {len(cron_errs)} 条错误/异常",
            "root_cause_hypothesis": "scan/push/bridge 脚本运行时失败",
            "evidence": {"samples": cron_errs[-5:]},
        })

    from .audit_dispatch import list_pending_audit_tasks
    pending_audit = list_pending_audit_tasks(data_dir, 500)
    if pending_audit:
        problems.append({
            "id": "R1-PENDING-AUDIT",
            "severity": "high",
            "category": "audit_backlog",
            "symptom": f"{len(pending_audit)} 个 pipeline 任务终态但无 audit_log（Dashboard 显示待审计）",
            "root_cause_hypothesis": "灵鉴未收到派单或未 POST /api/tasks/audit",
            "evidence": {
                "sample_task_ids": [t["task_id"] for t in pending_audit[:10]],
                "hint": "scan 会自动派 audit-req-* 给 lingjian；灵鉴须写 audit_log",
            },
        })

    gate = evaluate_round1_gate(data_dir, agents)

    diagnosis = {
        "round": 1,
        "generated_at": _now_iso(),
        "round1_gate": gate,
        "round2_unlocked": gate.get("round2_unlocked", False),
        "summary": {
            "problem_count": len(problems),
            "critical": sum(1 for p in problems if p["severity"] == "critical"),
            "high": sum(1 for p in problems if p["severity"] == "high"),
            "inbox_agents_overloaded": [a for a, s in inbox.items() if s["pending"] >= 50],
            "pipeline_running": len(tasks["pipeline_running"]),
            "msg_results_count": _msg_results_count(data_dir),
        },
        "inbox_stats": inbox,
        "task_stats": tasks,
        "problems": sorted(problems, key=lambda p: {"critical": 0, "high": 1, "medium": 2, "low": 3}[p["severity"]]),
        "next_round_input": "将 problems[] 传入 run_round2() 生成 backlog",
    }
    json_write(_iter_path(data_dir, "round-1-diagnosis.json"), diagnosis)
    return diagnosis


def run_round2(data_dir: str, agents: dict, diagnosis: Optional[dict] = None, force: bool = False) -> dict:
    """Round 2: 诊断 → 可执行工单（按角色分配）。须 Round1 门禁通过。"""
    gate = evaluate_round1_gate(data_dir, agents)
    if not force and not gate.get("round2_unlocked"):
        blocked = {
            "round": 2,
            "status": "blocked",
            "generated_at": _now_iso(),
            "reason": "Round1 未通过：须主任务 success + 灵鉴 audit pass/warn 后才可生成 Round2 工单",
            "round1_gate": gate,
            "blockers": gate.get("blockers", []),
            "next_action": [
                "1. 完成主任务 pipeline 执行（status=success）",
                "2. 灵鉴处理 audit-req-* 消息并 POST /api/tasks/audit",
                "3. 再运行: bus iteration --round 2",
            ],
        }
        json_write(_iter_path(data_dir, "round-2-backlog.json"), blocked)
        return blocked

    if diagnosis is None:
        diagnosis = json_read(_iter_path(data_dir, "round-1-diagnosis.json"), None)
    if not diagnosis:
        diagnosis = run_round1(data_dir, agents)

    items = []
    seq = 0
    inbox_agents_needing_cleanup = []

    def add(owner, role, title, actions, acceptance, deps=None, priority="P0"):
        nonlocal seq
        seq += 1
        items.append({
            "id": f"R2-{seq:03d}",
            "priority": priority,
            "owner": owner,
            "role": role,
            "title": title,
            "actions": actions,
            "acceptance": acceptance,
            "depends_on": deps or [],
            "status": "pending",
            "result_file": f"msg-results/iteration-r2-{seq:03d}.json",
        })

    for prob in diagnosis.get("problems", []):
        cat = prob.get("category", "")
        pid = prob.get("id", "")

        if cat == "inbox_backlog":
            inbox_agents_needing_cleanup.append(prob.get("agent", "unknown"))

        elif cat == "pipeline_stuck":
            for tid in prob.get("evidence", {}).get("task_ids", [])[:3]:
                assignee = _task_assignee(data_dir, tid) or "lingzhao"
                add(
                    owner=assignee,
                    role=_role_for_agent(assignee),
                    title=f"推进 pipeline 任务 {tid}",
                    actions=[
                        f"读取 inbox 中含【{tid}】的消息",
                        "执行 deliverable，写 msg-results/{tid}.json（含 next_role）",
                        "等待 scan → 确认 chain 推进到下一角色",
                    ],
                    acceptance=[
                        f"msg-results/{tid}.json 存在",
                        f"tracker status=running 且 chain step 增加或 status=success",
                    ],
                    priority="P0",
                )

        elif cat == "tracker_timeout" and pid == "R1-FALSE-TIMEOUT":
            add(
                owner="lingxiao",
                role="开发工程师",
                title="恢复误标 timeout 的 pipeline 任务",
                actions=[
                    "python docker-agents/reopen-pipeline-timeouts.py",
                    "确认 config reminder_minutes>=30 max_reminders>=12",
                    "bus scan 一轮，确认 reopen_stale_timeouts 日志",
                ],
                acceptance=[
                    f"{load_primary_task_id(data_dir)} status=running",
                    "false_timeout 列表为空",
                ],
                priority="P0",
            )

        elif cat == "ops":
            add(
                owner="lingxiao",
                role="开发工程师",
                title="修复 cron.log 异常",
                actions=[
                    "tail -50 store/cron.log 定位 traceback",
                    "修复对应脚本并跑 monitor-regression.sh",
                ],
                acceptance=["cron.log 5 分钟内无新 traceback"],
                priority="P1",
            )

    if inbox_agents_needing_cleanup:
        agents_str = ", ".join(sorted(set(inbox_agents_needing_cleanup)))
        add(
            owner="xiaoqi",
            role="调度员",
            title=f"inbox 减负（{agents_str}）",
            actions=[
                "读取 round-1-diagnosis.json inbox_stats",
                "对各积压 agent：archive 7天前 notice/reply，保留 type=task",
                "bus scan 验证 task 类型 urgent 优先推送",
                "更新 backlog 中 R2 项 status",
            ],
            acceptance=[
                "所有 listed agent inbox pending < 50",
                "mailbus-hardening 相关消息 pushed_count > 0",
            ],
            priority="P0",
        )

    # 固定闭环工单
    add(
        owner="lingzhao",
        role="方案设计师",
        title="汇总 Round2 方案并更新迭代文档",
        actions=[
            "阅读 store/iterations/round-1-diagnosis.json",
            "确认 R2 工单优先级，冲突项写入 ADR",
            "输出 plans/mailbus-iteration-round2-plan.md",
        ],
        acceptance=["plan.md 存在且引用全部 R2-id"],
        deps=[i["id"] for i in items[:-1][:5]],
        priority="P0",
    )
    add(
        owner="lingjian",
        role="审查官",
        title="审查 Round2 代码/配置变更",
        actions=[
            "git diff lib/tracker.py lib/scanner.py lib/scheduler.py lib/jobs.py",
            "确认不误伤 notice 自动 ack 逻辑",
        ],
        acceptance=["audit_log 或 msg-results 含 pass/fail"],
        priority="P1",
    )
    add(
        owner="lingyan",
        role="测试工程师",
        title="Round2 回归验证",
        actions=[
            "bash docker-agents/monitor-regression.sh",
            f"bash docker-agents/task-flow-snapshot.sh {load_primary_task_id(data_dir)}",
        ],
        acceptance=["monitor 9/9", "pipeline step >= 2 或 msg-results 存在"],
        priority="P0",
    )

    backlog = {
        "round": 2,
        "status": "ready",
        "generated_at": _now_iso(),
        "source": "round-1-diagnosis.json",
        "round1_gate": gate,
        "diagnosis_summary": diagnosis.get("summary", {}),
        "items": items,
        "dispatch_order": ["lingzhao", "xiaoqi", "lingxiao", "lingjian", "lingyan", "xiaoqi"],
        "next_round_input": "items[].status=all_done → run_round3()",
    }
    json_write(_iter_path(data_dir, "round-2-backlog.json"), backlog)
    return backlog


def run_round3(data_dir: str, agents: dict, backlog: Optional[dict] = None, force: bool = False) -> dict:
    """Round 3: 定义 agent 自迭代闭环协议。须 Round2 backlog status=ready。"""
    if backlog is None:
        backlog = json_read(_iter_path(data_dir, "round-2-backlog.json"), None)
    if not backlog:
        backlog = run_round2(data_dir, agents, force=force)
    if backlog.get("status") == "blocked" and not force:
        return {
            "round": 3,
            "status": "blocked",
            "reason": "Round2 未解锁，跳过 Round3",
            "round1_gate": backlog.get("round1_gate"),
        }

    pending = [i for i in backlog.get("items", []) if i.get("status") != "done"]
    done = [i for i in backlog.get("items", []) if i.get("status") == "done"]

    protocol = {
        "round": 3,
        "generated_at": _now_iso(),
        "source": "round-2-backlog.json",
        "loop": {
            "name": "mailbus-self-iteration",
            "period_minutes": 15,
            "steps": [
                {
                    "step": 1,
                    "actor": "mailbus-scan",
                    "action": "run_housekeeping + pipeline_trigger + iteration_engine.run_round1",
                    "output": "store/iterations/round-1-diagnosis.json",
                },
                {
                    "step": 2,
                    "actor": "lingzhao",
                    "trigger": "round1_gate.round2_unlocked == true（禁止 Round1 未完成时触发 Round2）",
                    "action": "读 round-1-gate.json → 通过后 bus iteration --round 2",
                    "output": "store/iterations/round-2-backlog.json",
                },
                {
                    "step": 3,
                    "actor": "各 R2.owner",
                    "trigger": "inbox 收到 type=task 且 content 含 R2-xxx",
                    "action": "执行 actions[] → 写 result_file → next_role=调度员",
                    "output": "msg-results/iteration-r2-NNN.json",
                },
                {
                    "step": 4,
                    "actor": "lingyan",
                    "trigger": "所有 P0 acceptance 可验证",
                    "action": "跑 monitor-regression + 更新 backlog item status=done",
                    "output": "msg-results/iteration-r3-verify.json",
                },
                {
                    "step": 5,
                    "actor": "xiaoqi",
                    "trigger": "Round2 全部 done 或 新一轮 critical 出现",
                    "action": "run_round3 → 决定是否启动下一轮 Round1",
                    "output": "store/iterations/round-3-protocol.json",
                },
            ],
        },
        "health_gates": {
            "unlock_round2": [
                "primary_task status=success",
                "primary_task audit_log.result in (pass, warn)",
            ],
            "proceed_to_next_round": [
                "round2_unlocked=true",
                "round-2-backlog 全部 P0 status=done",
            ],
            "abort_and_alert": [
                "cron.log 连续 3 次 scan traceback",
                "全部 agent inbox task_pending 无 pushed 超过 60min",
            ],
        },
        "agent_commands": _iteration_agent_commands(),
        "backlog_status": {
            "total": len(backlog.get("items", [])),
            "done": len(done),
            "pending": len(pending),
            "pending_ids": [i["id"] for i in pending[:10]],
        },
        "next_iteration_trigger": (
            "当 health_gates.proceed_to_next_round 全部满足时，"
            "由 xiaoqi 发起 iteration-round-N+1 任务（task_id=iteration-{date}-r1）"
        ),
    }
    json_write(_iter_path(data_dir, "round-3-protocol.json"), protocol)
    return protocol


def run_all(data_dir: str, agents: dict, force: bool = False) -> dict:
    d1 = run_round1(data_dir, agents)
    gate = d1.get("round1_gate") or evaluate_round1_gate(data_dir, agents)
    out = {
        "round1": d1["summary"],
        "round1_gate": gate,
        "round2_unlocked": gate.get("round2_unlocked", False),
    }
    if force or gate.get("round2_unlocked"):
        d2 = run_round2(data_dir, agents, d1, force=force)
        out["round2"] = {"status": d2.get("status", "ready"), "items": len(d2.get("items") or [])}
        if d2.get("status") != "blocked":
            d3 = run_round3(data_dir, agents, d2, force=force)
            out["round3"] = d3.get("backlog_status") or d3
    else:
        out["round2"] = {"status": "blocked", "reason": "等待 Round1 执行+审计通过"}
        out["round3"] = {"status": "skipped"}
    return out


def _iteration_agent_commands() -> dict:
    """Round 命令 — 使用 MAILBUS_ROOT，避免硬编码 /mnt/e/ai_tools/mail。"""
    root = str(MAILBUS_ROOT).replace("\\", "/")
    snap = f"{root}/docker-agents/task-flow-snapshot.sh"
    snap_cmd = f"bash {snap}" if os.path.isfile(snap) else f"bash docker-agents/task-flow-snapshot.sh"
    base = f"cd {root} && python bus.py iteration"
    return {
        "assess": f"{base} --round 1 --data-dir store",
        "plan": f"{base} --round 2 --data-dir store",
        "protocol": f"{base} --round 3 --data-dir store",
        "full_cycle": f"{base} --round all --data-dir store",
        "snapshot": snap_cmd,
    }


def _task_assignee(data_dir: str, task_id: str) -> Optional[str]:
    t = TaskTracker(data_dir).get(task_id)
    return t.get("assignee") if t else None


def _role_for_agent(agent_id: str) -> str:
    mapping = {
        "lingzhao": "方案设计师", "xiaoqi": "调度员", "lingxiao": "开发工程师",
        "dali": "开发工程师", "lingyun": "开发工程师", "lingjian": "审查官", "lingyan": "测试工程师",
        "lingjin": "安全审计师", "lingxi": "技术研究员",
    }
    return mapping.get(agent_id, "开发工程师")
