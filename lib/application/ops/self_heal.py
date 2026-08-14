"""mailbus 自愈 — 每轮 scan 自动推进，无需外部脚本。

职责：
- agent 回复 → msg-results 回收
- tracker / inbox 与 msg-results 对齐
- 无 CLI 进程的 processing 僵尸释放
- 历史噪音任务自动审计归档
"""

from __future__ import annotations

from lib.infra.clock import now_dt, now_ts, now_utc_dt
import glob
import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Set

from lib.domain.models import Inbox, MsgStatus
from lib.application.orchestration.tracker import TaskTracker, TaskStatus, SKIP_TIMEOUT_PREFIXES
from lib.infra.utils import json_read, json_write, resolve_paths, _now_iso
from lib.infra.mbus_log import debug

# 从消息正文提取 pipeline 任务 ID
_TASK_ID_RE = re.compile(r"【([a-zA-Z0-9_-]+)】")


def _default_reviewer(data_dir: str) -> str:
    """默认审查人 — org_defaults.reviewer（store config 可覆盖）。"""
    from lib.infra.org_defaults import org_default

    return org_default(data_dir, "reviewer")


def _docker_container(service: str) -> str:
    """解析 Docker 容器名：环境变量 > 默认 compose 命名。"""
    env_key = f"MAILBUS_CONTAINER_{service.upper().replace('-', '_')}"
    if os.environ.get(env_key):
        return os.environ[env_key]
    prefix = os.environ.get("MAILBUS_CONTAINER_PREFIX", "docker-agents")
    return f"{prefix}-{service}-1"


def agent_cli_active(agent_name: str, agents: dict) -> bool:
    """agent 容器内是否仍有可执行任务 CLI（非 dashboard）。"""
    from lib.composition import agent_cli_active as _adapter_cli_active
    return _adapter_cli_active(agent_name, agents)


def agent_cli_active_for(
    agent_name: str,
    agents: dict,
    *,
    msg_id: str = "",
    task_id: str = "",
) -> bool:
    from lib.composition import agent_cli_active_for as _for
    return _for(agent_name, agents, msg_id=msg_id, task_id=task_id)


def _extract_task_ids(text: str) -> Set[str]:
    if not text:
        return set()
    return set(_TASK_ID_RE.findall(text))


def _infer_next_role(from_agent: str, data_dir: str = "") -> str:
    from lib.application.orchestration.pipeline.chain import agent_to_role
    from lib.application.orchestration.role_flow import get_next_role
    role = agent_to_role(from_agent, data_dir)
    return get_next_role(role, "done") or "调度员"


def recover_replies_to_msg_results(data_dir: str, agents: dict) -> int:
    """从 mailbus 回复文件 / replies 目录回收 msg-results（仅限非 pipeline 根任务）。"""
    from lib.application.orchestration.pipeline.chain import is_pipeline_step

    written = 0
    results_dir = os.path.join(data_dir, "msg-results")
    os.makedirs(results_dir, exist_ok=True)
    tr = TaskTracker(data_dir)

    sources = []
    mailbus_dir = os.path.join(data_dir, "inbox", "mailbus")
    if os.path.isdir(mailbus_dir):
        sources.extend(glob.glob(os.path.join(mailbus_dir, "*-reply-*.json")))
    replies_dir = os.path.join(data_dir, "replies")
    if os.path.isdir(replies_dir):
        sources.extend(glob.glob(os.path.join(replies_dir, "*.json")))

    for path in sources:
        try:
            data = json_read(path, {})
        except (OSError, PermissionError, ValueError) as exc:
            debug(f"[self_heal] skip reply file {path}: {exc}")
            continue
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
            task = tr.get(tid)
            if task:
                chain = task.get("chain") or []
                if chain and is_pipeline_step(chain[0]):
                    continue
                assignee = task.get("assignee") or ""
                if from_agent and assignee and from_agent not in (assignee, "mailbus", "system"):
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
                "next_role": _infer_next_role(from_agent, data_dir),
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

        # msg-* tracker：禁止跨任务复制 msg-results（防串台）
        if tid.startswith("msg-") and not os.path.exists(result_path):
            summary = t.get("summary") or ""
            for ptid, ppath in primary_results.items():
                if ptid.startswith("msg-"):
                    continue
                if ptid not in summary:
                    continue
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
        from lib.application.orchestration.audit_dispatch import task_requires_audit
        if task_requires_audit(t):
            continue
        chain = t.get("chain") or []
        # 多步 pipeline 由 pipeline_trigger 推进，此处不强行 success
        if len(chain) > 1 or (chain and chain[0].get("planned_agents")):
            continue
        if chain and chain[-1].get("status") == "running":
            chain[-1]["status"] = "completed"
            chain[-1]["completed_at"] = _now_iso()
        t["status"] = TaskStatus.SUCCESS
        t["audit_reviewer"] = t.get("audit_reviewer") or _default_reviewer(data_dir)
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
                if task and task.get("status") == TaskStatus.RUNNING:
                    from lib.application.orchestration.pipeline.result_check import pipeline_step_result_matches
                    ok, _ = pipeline_step_result_matches(
                        data_dir, task, name, require_consumed=True,
                    )
                    if ok:
                        done = True
                        break
                    continue
                result_path = os.path.join(data_dir, "msg-results", f"{tid}.json")
                if os.path.exists(result_path):
                    if not task:
                        continue
                    if task.get("status") != TaskStatus.RUNNING:
                        done = True
                        break
                    continue
                if not task:
                    continue
                if task.get("status") != TaskStatus.RUNNING:
                    done = True
                    break
            if not done:
                entry = m if isinstance(m, dict) else {
                    "id": inbox.msg_field(m, "id", ""),
                    "type": inbox.msg_field(m, "type", ""),
                    "content": content,
                }
                from lib.application.orchestration.file_task_push import verify_file_task_delivery

                for mid in mids:
                    if not mid:
                        continue
                    probe = dict(entry)
                    probe["id"] = mid
                    ok, _ = verify_file_task_delivery(data_dir, name, probe)
                    if ok:
                        done = True
                        break
            if not done:
                continue
            for mid in mids:
                if mid and inbox.set_msg_status(
                    mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
                    done_at=_now_iso(), done_note="auto: task terminal or msg-results",
                    acknowledged_at=_now_iso(),
                ):
                    changed = True
                    stats["inbox_closed"] += 1
        if changed:
            json_write(inbox_file, inbox.to_dict())

    return stats


def _should_auto_audit(task: dict) -> bool:
    from lib.application.orchestration.audit_dispatch import NO_AUDIT_PREFIXES

    tid = task.get("task_id", "")
    if any(tid.startswith(p) for p in NO_AUDIT_PREFIXES):
        return True
    if any(tid.startswith(p) for p in SKIP_TIMEOUT_PREFIXES):
        return True
    summary = (task.get("summary") or "").strip().lower()
    if summary == "test":
        return True
    if task.get("requires_audit") is False:
        return True
    return False


def normalize_legacy_tracker_audit_flags(data_dir: str) -> int:
    """历史 msg-* tracker 标记为不要求审计；取消与 running pipeline 重复的 msg-* tracker。"""
    from lib.application.orchestration.pipeline.task import extract_task_id, get_running_pipeline_task

    tr = TaskTracker(data_dir)
    fixed = 0
    for task in tr.list_all():
        tid = task.get("task_id", "")
        if not tid.startswith("msg-"):
            continue
        summary = task.get("summary") or ""
        ptid = extract_task_id(summary)
        if ptid and get_running_pipeline_task(data_dir, ptid) and task.get("status") == "running":
            tr.update_status(tid, "cancelled", error={"reason": "duplicate msg-* pipeline tracker"})
            fixed += 1
            continue
        if task.get("requires_audit") is False:
            continue
        task["requires_audit"] = False
        if not task.get("audit_log"):
            task.pop("audit_reviewer", None)
            task.pop("audit_dispatched_at", None)
        json_write(tr._task_path(tid), task)
        fixed += 1
    return fixed


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
            reviewer=audit.get("reviewer") or _default_reviewer(data_dir),
            result=audit.get("result", "warn"),
            issues=list(audit.get("issues") or []) + ["inherited from primary pipeline audit"],
            summary=f"继承主任务 {primary} 审计",
            category=audit.get("category", "code_review"),
        )
        linked += 1
    return linked


def trim_stale_notices(data_dir: str, agents: dict, max_age_days: int = 3) -> int:
    """关闭超期 pending 系统 notice，减轻 inbox 积压（根因：历史通知未归档）。"""
    from lib.application.orchestration.tracker import _parse_iso_dt

    paths = resolve_paths(data_dir)
    cutoff = now_utc_dt() - timedelta(days=max_age_days)
    markers = ("规则更新", "团队规范", "rule-change", "bulletin", "📢", "team-secrets", "execution-order")
    trimmed = 0
    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            continue
        inbox = Inbox.from_dict(inbox_data)
        changed = False
        for m in inbox.messages:
            state = inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")
            if state not in (MsgStatus.PENDING, MsgStatus.PUSHED, "sent", "new"):
                continue
            if inbox.msg_field(m, "type", "") not in ("notice", "system"):
                continue
            content = inbox.msg_field(m, "content", "") or ""
            if not any(x in content for x in markers):
                continue
            created = inbox.msg_field(m, "created_at", "")
            try:
                if created and _parse_iso_dt(created) >= cutoff:
                    continue
            except Exception:
                pass
            mid = inbox.msg_field(m, "id", "")
            if mid and inbox.set_msg_status(
                mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
                done_at=_now_iso(), done_note="auto: stale system notice trimmed",
            ):
                trimmed += 1
                changed = True
        if changed:
            json_write(inbox_file, inbox.to_dict())
    return trimmed


def run_self_heal(data_dir: str, agents: dict, *, phase: str = "full") -> dict:
    """scan 内置自愈入口。pre=推送前，full=含审计归档。"""
    out = {}
    try:
        from lib.application.transport.delivery_normalizer import normalize_opencode_deliveries
        norm = normalize_opencode_deliveries(data_dir, agents)
        if norm.get("total"):
            out["delivery_normalized"] = norm["total"]
    except Exception as exc:
        debug(f"[self_heal] delivery_normalizer error: {exc}")
    n = recover_replies_to_msg_results(data_dir, agents)
    if n:
        out["reply_recovered"] = n
    sync = sync_tracker_and_inbox(data_dir, agents)
    out.update({k: v for k, v in sync.items() if v})
    try:
        from lib.application.orchestration.execution import run_orchestrator
        orch = run_orchestrator(data_dir, agents, fix=True, mode="light")
        if orch.get("reconcile"):
            out.update({f"orch_{k}": v for k, v in orch["reconcile"].items() if v})
        if orch.get("anomaly_count"):
            out["anomalies"] = orch["anomaly_count"]
    except Exception:
        pass
    if phase == "full":
        n = trim_stale_notices(data_dir, agents)
        if n:
            out["notices_trimmed"] = n
        n = normalize_legacy_tracker_audit_flags(data_dir)
        if n:
            out["msg_tracker_audit_flags"] = n
        n = auto_close_stale_audits(data_dir)
        if n:
            out["audits_auto_closed"] = n
        n = link_msg_tracker_audits(data_dir)
        if n:
            out["msg_audit_linked"] = n
    return out
