"""mailbus 自愈 — 每轮 scan 自动推进，无需外部脚本。

职责：
- agent 回复 → msg-results 回收
- tracker / inbox 与 msg-results 对齐
- 无 CLI 进程的 processing 僵尸释放
- 历史噪音任务自动审计归档
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
from typing import Dict, Optional, Set

from .models import Inbox, MsgStatus
from .tracker import TaskTracker, TaskStatus, SKIP_TIMEOUT_PREFIXES
from .utils import json_read, json_write, resolve_paths, _now_iso

# 从消息正文提取 pipeline 任务 ID
_TASK_ID_RE = re.compile(r"【([a-zA-Z0-9_-]+)】")


def agent_cli_active(agent_name: str, agents: dict) -> bool:
    """agent 容器内是否仍有可执行任务 CLI（非 dashboard）。"""
    agent = agents.get(agent_name) or {}
    cmd = ((agent.get("launch") or {}).get("cli") or {}).get("command", "")
    if not cmd:
        return False
    try:
        if "openclaw" in cmd:
            r = subprocess.run(
                ["docker", "exec", "docker-agents-openclaw-1", "ps", "aux"],
                capture_output=True, text=True, timeout=8,
            )
            return "openclaw tui" in r.stdout
        if "cline" in cmd:
            container = "docker-agents-dali-1" if agent_name == "dali" else "docker-agents-lingxiao-1"
            r = subprocess.run(
                ["docker", "exec", container, "ps", "aux"],
                capture_output=True, text=True, timeout=8,
            )
            return bool(re.search(r"cline.*-q", r.stdout))
        if "hermes chat" in cmd:
            profile = agent.get("profile") or agent_name
            r = subprocess.run(
                ["docker", "exec", "docker-agents-hermes-1", "ps", "aux"],
                capture_output=True, text=True, timeout=8,
            )
            return bool(re.search(rf"profile {re.escape(profile)}.*hermes chat", r.stdout))
    except Exception:
        return False
    return False


def _extract_task_ids(text: str) -> Set[str]:
    if not text:
        return set()
    return set(_TASK_ID_RE.findall(text))


def _infer_next_role(from_agent: str) -> str:
    from .pipeline_chain import agent_to_role
    from .role_flow import get_next_role
    role = agent_to_role(from_agent)
    return get_next_role(role, "done") or "调度员"


def recover_replies_to_msg_results(data_dir: str, agents: dict) -> int:
    """从 mailbus 回复文件 / replies 目录回收 msg-results。"""
    written = 0
    results_dir = os.path.join(data_dir, "msg-results")
    os.makedirs(results_dir, exist_ok=True)

    sources = []
    mailbus_dir = os.path.join(data_dir, "inbox", "mailbus")
    if os.path.isdir(mailbus_dir):
        sources.extend(glob.glob(os.path.join(mailbus_dir, "*-reply-*.json")))
    replies_dir = os.path.join(data_dir, "replies")
    if os.path.isdir(replies_dir):
        sources.extend(glob.glob(os.path.join(replies_dir, "*.json")))

    for path in sources:
        data = json_read(path, {})
        if not data:
            continue
        content = data.get("content") or data.get("reply") or ""
        if not content or len(content) < 20:
            continue
        from_agent = data.get("from") or data.get("agent") or ""
        msg_id = data.get("msg_id") or ""
        task_ids = _extract_task_ids(content)
        if not task_ids and msg_id:
            # 尝试从关联 inbox 消息推断
            for agent in agents:
                inbox = json_read(f"{resolve_paths(data_dir)['inbox']}/{agent}/inbox.json", {})
                for m in inbox.get("messages", []):
                    if m.get("id") == msg_id:
                        task_ids = _extract_task_ids(m.get("content", ""))
                        break
        for tid in task_ids:
            if tid.startswith("msg-"):
                continue
            out = os.path.join(results_dir, f"{tid}.json")
            if os.path.exists(out):
                continue
            summary = content.strip()
            if len(summary) > 400:
                summary = summary[:400] + "…"
            payload = {
                "template": "report",
                "conclusion": "done",
                "task": tid,
                "summary": summary,
                "next_role": _infer_next_role(from_agent or "lingzhao"),
                "source": "auto-recovered-from-reply",
                "msg_id": msg_id,
                "agent": from_agent,
                "timestamp": data.get("timestamp") or _now_iso(),
            }
            json_write(out, payload)
            written += 1
    return written


def sync_tracker_and_inbox(data_dir: str, agents: dict) -> Dict[str, int]:
    """msg-results 已存在 → 关闭 tracker/inbox；主任务结果关联 msg-* tracker。"""
    paths = resolve_paths(data_dir)
    tr = TaskTracker(data_dir)
    stats = {"tracker_closed": 0, "inbox_closed": 0, "linked": 0}

    # 主任务 msg-results 索引（按 summary 关键词）
    primary_results = {}
    for f in glob.glob(os.path.join(data_dir, "msg-results", "*.json")):
        base = os.path.basename(f)
        if base.startswith("audit-") or base.startswith("iteration-"):
            continue
        data = json_read(f, {})
        tid = data.get("task") or base[:-5]
        primary_results[tid] = f

    for t in tr.list_all():
        tid = t.get("task_id", "")
        if not tid:
            continue
        result_path = os.path.join(data_dir, "msg-results", f"{tid}.json")

        # msg-* tracker：若 summary 含已有 msg-results 的主 task_id，复制关联
        if tid.startswith("msg-") and not os.path.exists(result_path):
            summary = t.get("summary") or ""
            for ptid, ppath in primary_results.items():
                if ptid in summary and not ptid.startswith("msg-"):
                    data = dict(json_read(ppath, {}))
                    data["task"] = tid
                    data["msg_id"] = tid
                    data["source"] = f"auto-linked-from-{ptid}"
                    json_write(result_path, data)
                    stats["linked"] += 1
                    break

        if not os.path.exists(result_path):
            continue
        if t.get("status") in (TaskStatus.SUCCESS, TaskStatus.CANCELLED):
            continue
        chain = t.get("chain") or []
        # 多步 pipeline 由 pipeline_trigger 推进，此处不强行 success
        if len(chain) > 1 or (chain and chain[0].get("planned_agents")):
            continue
        if chain and chain[-1].get("status") == "running":
            chain[-1]["status"] = "completed"
            chain[-1]["completed_at"] = _now_iso()
        t["status"] = TaskStatus.SUCCESS
        t["audit_reviewer"] = t.get("audit_reviewer") or "lingjian"
        json_write(tr._task_path(tid), t)
        stats["tracker_closed"] += 1

    # inbox：终态 task 消息标记 done
    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            continue
        inbox = Inbox.from_dict(inbox_data)
        changed = False
        for m in inbox.messages:
            state = inbox.msg_field(m, "state", "")
            if state in (MsgStatus.DONE, MsgStatus.ARCHIVED):
                continue
            if inbox.msg_field(m, "type", "") != "task":
                continue
            content = inbox.msg_field(m, "content", "")
            mids = {inbox.msg_field(m, "id", "")}
            tids = _extract_task_ids(content)
            done = False
            for tid in tids:
                task = tr.get(tid)
                if task and task.get("status") in (TaskStatus.SUCCESS, TaskStatus.CANCELLED):
                    done = True
                    break
                if os.path.exists(os.path.join(data_dir, "msg-results", f"{tid}.json")):
                    # 有结果且 tracker 不存在或非 running
                    if not task or task.get("status") != TaskStatus.RUNNING:
                        done = True
                        break
            if not done:
                continue
            for mid in mids:
                if mid and inbox.set_msg_status(
                    mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
                    done_at=_now_iso(), done_note="auto: task terminal or msg-results",
                ):
                    changed = True
                    stats["inbox_closed"] += 1
        if changed:
            json_write(inbox_file, inbox.to_dict())

    return stats


def _should_auto_audit(task: dict) -> bool:
    tid = task.get("task_id", "")
    if any(tid.startswith(p) for p in SKIP_TIMEOUT_PREFIXES):
        return True
    summary = (task.get("summary") or "").strip().lower()
    if summary == "test":
        return True
    created = task.get("created_at") or ""
    status = task.get("status")
    if created and created < "2026-06-14":
        return True
    if status in (TaskStatus.TIMEOUT, TaskStatus.FAILED) and created and created < "2026-06-15":
        return True
    if tid.startswith("lingzhao-") and "20260608" in tid:
        return True
    return False


def auto_close_stale_audits(data_dir: str) -> int:
    """历史/噪音终态任务自动 audit_log，避免 Dashboard 待审计堆积。"""
    tr = TaskTracker(data_dir)
    closed = 0
    for task in tr.list_all():
        if task.get("audit_log"):
            continue
        if task.get("status") not in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT):
            continue
        tid = task.get("task_id", "")
        if not _should_auto_audit(task):
            continue
        tr.add_audit(
            task_id=tid,
            reviewer="mailbus",
            result="warn",
            summary=f"自动归档审计（{task.get('status')}）",
            issues=["auto-closed by mailbus self_heal"],
            category="auto_archive",
        )
        closed += 1
    return closed


def link_msg_tracker_audits(data_dir: str) -> int:
    """msg-* tracker 与主任务 pipeline 关联时，继承主任务 audit_log。"""
    tr = TaskTracker(data_dir)
    primary = json_read(os.path.join(data_dir, "iterations", "iteration-state.json"), {}).get("primary_task_id", "")
    if not primary:
        return 0
    primary_task = tr.get(primary)
    if not primary_task or not primary_task.get("audit_log"):
        return 0
    audit = primary_task["audit_log"][-1]
    linked = 0
    for task in tr.list_all():
        tid = task.get("task_id", "")
        if not tid.startswith("msg-"):
            continue
        if task.get("audit_log"):
            continue
        if task.get("status") not in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT):
            continue
        summary = task.get("summary") or ""
        if primary not in summary and "scheduler-validation" not in summary:
            continue
        tr.add_audit(
            task_id=tid,
            reviewer=audit.get("reviewer", "lingjian"),
            result=audit.get("result", "warn"),
            issues=list(audit.get("issues") or []) + ["inherited from primary pipeline audit"],
            summary=f"继承主任务 {primary} 审计",
            category=audit.get("category", "code_review"),
        )
        linked += 1
    return linked


def run_self_heal(data_dir: str, agents: dict, *, phase: str = "full") -> dict:
    """scan 内置自愈入口。pre=推送前，full=含审计归档。"""
    out = {}
    n = recover_replies_to_msg_results(data_dir, agents)
    if n:
        out["reply_recovered"] = n
    sync = sync_tracker_and_inbox(data_dir, agents)
    out.update({k: v for k, v in sync.items() if v})
    try:
        from .execution_orchestrator import run_orchestrator
        orch = run_orchestrator(data_dir, agents, fix=True, mode="light")
        if orch.get("reconcile"):
            out.update({f"orch_{k}": v for k, v in orch["reconcile"].items() if v})
        if orch.get("anomaly_count"):
            out["anomalies"] = orch["anomaly_count"]
    except Exception:
        pass
    if phase == "full":
        n = auto_close_stale_audits(data_dir)
        if n:
            out["audits_auto_closed"] = n
        n = link_msg_tracker_audits(data_dir)
        if n:
            out["msg_audit_linked"] = n
    return out
