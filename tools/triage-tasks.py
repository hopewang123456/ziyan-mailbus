#!/usr/bin/env python3
"""盘点待审计/待处理任务 + Round2 消息状态。"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.utils import json_read, resolve_paths

DATA = os.environ.get("MAILBUS_DATA", "store")
SKIP_PREFIX = (
    "remind-", "tracker-remind-", "patrol-", "heartbeat-",
    "confirm-", "rule-change-", "alert-task-",
)


def _inbox_messages(inbox_data) -> list:
    if isinstance(inbox_data, list):
        return inbox_data
    if isinstance(inbox_data, dict):
        return inbox_data.get("messages", [])
    return []


def load_round2_messages(data_dir: str) -> dict[str, str]:
    """从 round-2-backlog dispatch 或 iteration-r2 tracker 动态解析 Round2 消息。"""
    found: dict[str, str] = {}
    backlog = json_read(os.path.join(data_dir, "iterations", "round-2-backlog.json"), {})
    for item in backlog.get("items") or []:
        owner = item.get("owner")
        mid = item.get("msg_id") or item.get("dispatch_msg_id")
        if owner and mid:
            found[mid] = owner

    for f in sorted(glob.glob(os.path.join(data_dir, "tasks", "msg-*.json"))):
        t = json_read(f, {})
        tid = t.get("task_id", os.path.basename(f).replace(".json", ""))
        summary = t.get("summary") or ""
        if "Round2" not in summary and "R2-" not in summary and "iteration-r2" not in summary:
            continue
        assignee = t.get("assignee") or ""
        if assignee and tid.startswith("msg-"):
            found.setdefault(tid, assignee)

    # 兜底：扫描各 agent inbox 中带 Round2/R2- 的 task
    paths = resolve_paths(data_dir)
    for agent_dir in glob.glob(os.path.join(paths["inbox"], "*")):
        if not os.path.isdir(agent_dir):
            continue
        agent = os.path.basename(agent_dir)
        inbox = json_read(os.path.join(agent_dir, "inbox.json"), {})
        for m in _inbox_messages(inbox):
            content = m.get("content") or ""
            if "Round2" in content or "R2-" in content:
                mid = m.get("id", "")
                if mid.startswith("msg-"):
                    found.setdefault(mid, agent)
    return found


def load_tasks():
    out = {"pending_audit": [], "running": [], "pending": [], "terminal": []}
    for f in sorted(glob.glob(os.path.join(DATA, "tasks", "*.json"))):
        t = json.load(open(f, encoding="utf-8"))
        tid = t.get("task_id", os.path.basename(f).replace(".json", ""))
        if any(tid.startswith(p) for p in SKIP_PREFIX):
            continue
        st = t.get("status", "")
        has_audit = bool(t.get("audit_log"))
        chain = t.get("chain") or []
        step = chain[-1] if chain else {}
        row = {
            "id": tid,
            "status": st,
            "summary": (t.get("summary") or "")[:50],
            "assignee": step.get("to_person") or t.get("assignee"),
            "step_role": step.get("to_role"),
            "step_status": step.get("status"),
            "has_audit": has_audit,
            "has_msg_results": os.path.exists(os.path.join(DATA, "msg-results", f"{tid}.json")),
        }
        if st in ("success", "failed", "timeout") and not has_audit:
            out["pending_audit"].append(row)
        elif st == "running":
            out["running"].append(row)
        elif st == "pending":
            out["pending"].append(row)
        else:
            out["terminal"].append(row)
    return out


def msg_state(agent, mid):
    paths = resolve_paths(DATA)
    inbox = json_read(f"{paths['inbox']}/{agent}/inbox.json", {})
    for m in _inbox_messages(inbox):
        if m.get("id") == mid:
            return {
                "agent": agent,
                "id": mid,
                "state": m.get("state"),
                "status": m.get("status"),
                "pushed_count": m.get("pushed_count", 0),
                "priority": m.get("priority"),
            }
    return {"agent": agent, "id": mid, "state": "missing"}


def main():
    tasks = load_tasks()
    print("=== 待审计 (终态无 audit_log) ===", len(tasks["pending_audit"]))
    for r in tasks["pending_audit"][:15]:
        print(f"  {r['id']}: {r['status']} assignee={r['assignee']}")
    if len(tasks["pending_audit"]) > 15:
        print(f"  ... +{len(tasks['pending_audit']) - 15} more")

    print("\n=== 执行中 ===", len(tasks["running"]))
    for r in tasks["running"]:
        mr = "Y" if r["has_msg_results"] else "N"
        print(f"  {r['id']}: step={r['step_role']}/{r['assignee']}({r['step_status']}) msg-results={mr}")

    print("\n=== pending ===", len(tasks["pending"]))
    for r in tasks["pending"][:10]:
        print(f"  {r['id']}: assignee={r['assignee']}")

    print("\n=== Round2 消息状态 ===")
    r2 = load_round2_messages(DATA)
    if not r2:
        print("  (无 Round2 消息记录)")
    for mid, agent in sorted(r2.items()):
        print(" ", msg_state(agent, mid))

    audit_pending = sum(
        1 for m in _inbox_messages(json_read(f"{resolve_paths(DATA)['inbox']}/lingjian/inbox.json", {}))
        if str(m.get("content", "")).startswith("【audit:")
        and m.get("state") not in ("done", "archived")
    )
    print(f"\n=== 灵鉴 audit inbox 活跃 === {audit_pending}")


if __name__ == "__main__":
    main()
