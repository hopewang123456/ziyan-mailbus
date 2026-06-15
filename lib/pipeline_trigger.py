"""pipeline_trigger.py — 文件通信 pipeline 检测

在 run_housekeeping 中被调用。检查所有有 chain 的任务，
如果 msg-results 中有对应的结果文件，自动推进到下一步。

所有 agent 统一走文件通信模式（杜绝 auto-ack）。"""

import os
import time
import glob as _glob
from .tracker import TaskTracker
from .role_flow import get_next_role, pick_person_for_role
from .pipeline_chain import normalize_task_chain, is_pipeline_step
from .models import Inbox
from .utils import json_read, json_write, _now_iso

VALID_ROLES = {"方案设计师","调度员","开发工程师","审查官","测试工程师","验收员","安全审计师","技术研究员","巡检官","运营"}

def trigger(data_dir: str, agents: dict, paths: dict):
    """主入口：扫描所有任务链，检测结果文件并推进"""
    TRA = TaskTracker(data_dir)
    for t in TRA.list_all():
        task_id = t.get("task_id", t.get("id", ""))
        task_file = os.path.join(TRA.tasks_dir, "%s.json" % task_id)
        raw_chain = t.get("chain")
        t = normalize_task_chain(t)
        if t.get("chain") != raw_chain:
            json_write(task_file, t)
        chain = t.get("chain", [])
        if not chain or not is_pipeline_step(chain[0]):
            continue
        current = chain[-1]
        status = current.get("status", "")
        if status in ("completed", "done"):
            # 如果所有步骤都完成了但 task.status 还不是 success，修复它
            all_done = all(s.get("status") in ("completed", "done") for s in chain)
            if all_done and t.get("status") != "success":
                t["status"] = "success"
                t["audit_reviewer"] = t.get("audit_reviewer") or "lingjian"
                task_file = os.path.join(TRA.tasks_dir, "%s.json" % t.get("task_id", "unknown"))
                json_write(task_file, t)
                print("  [pipeline] task.status -> success (全链完成) %s" % t.get("task_id", "?")[:30])
            continue
        to_person = current.get("to_person", "")
        if not to_person:
            continue

        result_file = _find_result(data_dir, t.get("task_id", t.get("id", "")))
        if not result_file:
            continue

        try:
            result = json_read(result_file, {})
        except Exception:
            continue

        if not _is_done(result):
            continue

        summary = result.get("summary", "") or result.get("result", {}).get("message", "") or result.get("task", "")
        report = {"conclusion": "done", "summary": summary, "template": "report", "details": result}

        current_role = current.get("to_role", "")
        n_role = result.get("next_role") or get_next_role(current_role, result.get("conclusion") or "done")
        if not n_role or n_role == current_role:
            # next_role 为空且规则表无匹配 → 全链完成
            current["status"] = "completed"
            current["completed_at"] = _now_iso()
            current["report"] = report
            t["status"] = "success"
            t["audit_reviewer"] = t.get("audit_reviewer") or "lingjian"
            task_file = os.path.join(TRA.tasks_dir, "%s.json" % t.get("task_id", "unknown"))
            json_write(task_file, t)
            print("  [pipeline] ✅ 全链完成! %s" % task_id)
            continue

        n_person = pick_person_for_role(n_role)
        if not n_person:
            print("  [pipeline] %s 无对应执行人" % n_role)
            continue

        current["status"] = "completed"
        current["completed_at"] = _now_iso()
        current["report"] = report
        chain.append({"step": len(chain) + 1, "from_role": current_role, "from_person": to_person, "to_role": n_role, "to_person": n_person, "action": "等待%s处理" % n_role, "status": "running", "started_at": _now_iso(), "completed_at": None, "report": None})
        print("  [pipeline] %s 完成 -> %s(%s)" % (to_person, n_role, n_person))

        _send_task(data_dir, paths, to_person, current_role, n_role, n_person, summary, task_id)

        t["assignee"] = n_person
        t["status"] = "running"
        task_file = os.path.join(TRA.tasks_dir, "%s.json" % task_id)
        json_write(task_file, t)


def _find_result(data_dir, task_id):
    """查找结果文件，兼容 task_id 和 msg_id 两种命名"""
    f = os.path.join(data_dir, "msg-results", "%s.json" % task_id)
    if os.path.exists(f):
        return f
    flist = _glob.glob(os.path.join(data_dir, "msg-results", "msg-*%s*.json" % task_id[-8:]))
    if flist:
        return flist[0]
    return None


def _is_done(result):
    """判断结果文件是否表示任务已完成"""
    c = result.get("conclusion", "")
    if c in ("done", "pass", "approved", "fail"):
        return True
    if result.get("status") == "completed":
        return True
    if result.get("task"):
        return True
    return False

def _send_task(data_dir, paths, from_person, from_role, to_role, to_person, summary, task_id=""):
    """写任务文件和推送消息给下一步的 agent"""
    nid = "pipeline-%d" % int(time.time())
    nf = os.path.join(data_dir, "msg-files", "%s.md" % nid)
    rf = os.path.join(data_dir, "msg-results", "%s.json" % (task_id or nid))

    try:
        os.makedirs(os.path.join(data_dir, "msg-files"), exist_ok=True)
        with open(nf, "w") as xf:
            xf.write("# %s\n\n来自: %s(%s)\n\n## 任务描述\n请执行当前角色职责：%s\n\n## 角色配置\n请参阅 %s/rules/role-flow-config.md\n\n## 上一步产出\n%s\n\n## 完成条件\n将结论写入 %s\n\n## 结果格式（必须遵守）\n```json\n{\"template\":\"report\",\"conclusion\":\"pass|fail|done\",\"summary\":\"<结论>\",\"next_role\":\"审查官\"}\n```\n\n## next_role 可选值\n- 审查官（开发完成）\n- 测试工程师（审查通过）\n- 验收员（测试通过）\n- 方案设计师（遇到阻塞）" % (to_role, from_role, from_person, to_role, data_dir, summary[:500], rf))
    except Exception:
        nf = ""

    nxt_file = os.path.join(paths["inbox"], to_person, "inbox.json")
    if not os.path.exists(os.path.dirname(nxt_file)):
        return

    nxt_data = json_read(nxt_file, {})
    nxt_inbox = Inbox.from_dict(nxt_data) if nxt_data else Inbox(agent=to_person)
    nxt_inbox.messages.append({"id": nid, "from": from_person, "to": to_person, "type": "task", "priority": "normal", "state": "pending",
        "content": "📋 新任务\n任务文件: %s\n结果写入: %s\n请读取任务文件执行，完成后写结果文件。\n\n⚠️ 必须写入结果文件才能完成。" % (nf, rf),
        "created_at": _now_iso()})
    nxt_inbox.has_unread = True
    json_write(nxt_file, nxt_inbox.to_dict())
    print("  [pipeline] 已推送消息给 %s" % to_person)
