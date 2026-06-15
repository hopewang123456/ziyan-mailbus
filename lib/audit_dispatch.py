"""待审计任务派单给灵鉴 + 回收 audit msg-results。"""

import os
import re
from typing import List

from .tracker import TaskTracker, TaskStatus, SKIP_TIMEOUT_PREFIXES
from .pipeline_chain import is_pipeline_step
from .models import Inbox
from .utils import json_read, json_write, _now_iso

AUDIT_REVIEWER = "lingjian"
TERMINAL = {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.TIMEOUT}
MAX_DISPATCH_PER_SCAN = 2


def _is_noise_task(task_id: str, summary: str = "") -> bool:
    if any(task_id.startswith(p) for p in SKIP_TIMEOUT_PREFIXES):
        return True
    s = (summary or "")[:80]
    return s.startswith("⚠️ 超时提醒") or s.startswith("⏰ 催办提醒")


def _needs_audit(task: dict) -> bool:
    tid = task.get("task_id", "")
    if _is_noise_task(tid, task.get("summary", "")):
        return False
    chain = task.get("chain") or []
    if not chain:
        return False
    if isinstance(chain[0], dict) and (
        is_pipeline_step(chain[0]) or chain[0].get("planned_agents") or chain[0].get("to_role")
    ):
        return True
    return bool(chain[0].get("agent"))

def list_pending_audit_tasks(data_dir: str, limit: int = 50) -> List[dict]:
    tracker = TaskTracker(data_dir)
    out = []
    for task in tracker.list_all():
        if task.get("status") not in TERMINAL:
            continue
        if task.get("audit_log"):
            continue
        if not _needs_audit(task):
            continue
        out.append(task)
    out.sort(
        key=lambda t: t.get("updated_at", t.get("created_at", "")),
        reverse=True,
    )
    return out[:limit]


def _already_dispatched(task: dict) -> bool:
    return bool(task.get("audit_dispatched_at"))


def dispatch_pending_audits(data_dir: str, agents: dict, paths: dict) -> int:
    """将待审计任务派给灵鉴 inbox，每轮 scan 最多 MAX_DISPATCH_PER_SCAN 条。"""
    if AUDIT_REVIEWER not in agents:
        return 0

    tracker = TaskTracker(data_dir)
    pending = [t for t in list_pending_audit_tasks(data_dir, 100) if not _already_dispatched(t)]
    if not pending:
        return 0

    # Round1 主任务优先审计
    try:
        from .iteration_engine import load_iteration_state
        primary = load_iteration_state(data_dir).get("primary_task_id", "")
        if primary:
            pending.sort(
                key=lambda t: (0 if t.get("task_id") == primary else 1,
                               t.get("updated_at", t.get("created_at", ""))),
                reverse=False,
            )
            # updated_at 仍要新的在前：对非 primary 反向
            primary_tasks = [t for t in pending if t.get("task_id") == primary]
            other = [t for t in pending if t.get("task_id") != primary]
            other.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
            pending = primary_tasks + other
    except Exception:
        pass

    inbox_file = f"{paths['inbox']}/{AUDIT_REVIEWER}/inbox.json"
    inbox_data = json_read(inbox_file, {})
    inbox = Inbox.from_dict(inbox_data) if inbox_data else Inbox(agent=AUDIT_REVIEWER)

    dispatched = 0
    for task in pending[:MAX_DISPATCH_PER_SCAN]:
        tid = task["task_id"]
        status = task.get("status", "?")
        summary = (task.get("summary") or "")[:120]
        msg_id = f"audit-req-{tid}"[:80]
        # 避免重复写入
        if any(inbox.msg_field(m, "id", "") == msg_id for m in inbox.messages):
            task["audit_dispatched_at"] = task.get("audit_dispatched_at") or _now_iso()
            json_write(tracker._task_path(tid), task)
            continue

        content = f"""【audit:{tid}】请灵鉴审计以下任务（Round1 门禁：审计通过后才会进入 Round2）

任务 ID: {tid}
终态: {status}
摘要: {summary}
负责人(末次): {task.get('assignee', '?')}

请完成：
1. 阅读 tracker 任务与相关 msg-results / 代码变更
2. 给出 pass / fail / warn 及具体问题
3. 任选其一提交审计结论：
   - POST /api/tasks/audit  body: {{"task_id":"{tid}","reviewer":"lingjian","result":"pass|fail|warn","summary":"..."}}
   - 或写 store/msg-results/audit-{tid}.json（含 audit:true, result, summary, issues[]）

⚠️ 仅 ACK 不算完成；Dashboard「待审计」依赖 audit_log 写入。"""

        import time as _time
        inbox.messages.append({
            "id": msg_id,
            "from": "mailbus",
            "to": AUDIT_REVIEWER,
            "type": "task",
            "priority": "urgent",
            "state": "pending",
            "content": content,
            "created_at": _now_iso(),
            "action": {"ack": True, "execute": True, "store_memory": False},
        })
        inbox.has_unread = True
        task["audit_dispatched_at"] = _now_iso()
        task["audit_reviewer"] = AUDIT_REVIEWER
        json_write(tracker._task_path(tid), task)
        dispatched += 1

    if dispatched:
        json_write(inbox_file, inbox.to_dict())
        print(f"  🔍 已派 {dispatched} 条待审计任务 → {AUDIT_REVIEWER}")
    return dispatched


def consume_audit_results(data_dir: str) -> int:
    """读取 msg-results/audit-*.json 并写入 tracker.audit_log。"""
    results_dir = os.path.join(data_dir, "msg-results")
    if not os.path.isdir(results_dir):
        return 0

    tracker = TaskTracker(data_dir)
    consumed = 0
    for fname in os.listdir(results_dir):
        if not fname.startswith("audit-") or not fname.endswith(".json"):
            continue
        fpath = os.path.join(results_dir, fname)
        data = json_read(fpath, {})
        if not data.get("audit") and not data.get("result"):
            continue
        tid = data.get("task_id") or fname[6:-5]  # audit-{tid}.json
        if not tid:
            continue
        task = tracker.get(tid)
        if not task or task.get("audit_log"):
            continue
        result = data.get("result", "warn")
        if result not in ("pass", "fail", "warn"):
            result = "warn"
        tracker.add_audit(
            task_id=tid,
            reviewer=data.get("agent") or data.get("reviewer") or AUDIT_REVIEWER,
            result=result,
            issues=data.get("issues") or [],
            summary=data.get("summary", "") or data.get("message", ""),
            category=data.get("category", "code_review"),
            severity=data.get("severity", "normal"),
        )
        consumed += 1
        print(f"  ✓ 审计已入库: {tid} → {result}")

    return consumed
