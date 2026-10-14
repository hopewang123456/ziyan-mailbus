#!/usr/bin/env python3
"""Inbox 待处理摘要 — 查看指定 agent 的 pending/processing 消息。"""
import argparse, json, os, sys, urllib.request

MAIL_API = os.environ.get("MAILBUS_URL", "http://127.0.0.1:9814")

def api_get(path):
    try:
        req = urllib.request.Request(f"{MAIL_API}{path}", headers={"User-Agent": "clinic/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def main():
    ap = argparse.ArgumentParser(description="Inbox pending dump")
    ap.add_argument("--agent", default="agent-a", help="agent name")
    args = ap.parse_args()

    status = api_get("/api/status")
    agents = status.get("agent_statuses", {})
    info = agents.get(args.agent)
    if not info:
        print(f"Agent '{args.agent}' not found in status")
        return 1

    print(f"Agent: {args.agent}  type={info.get('type', '?')}  msgs={info.get('active_messages', 0)}")
    print(f"has_unread: {info.get('has_unread', False)}")

    workload = api_get("/api/workload")
    wl = (workload.get("agents") or {}).get(args.agent, {})
    print(f"inbox_pending: {wl.get('inbox_pending', 0)}")
    print(f"active_tasks: {wl.get('active_tasks', 0)}")
    print(f"queued_steps: {wl.get('queued_steps', 0)}")

    stats = api_get("/api/stats")
    agent_stats = (stats.get("agent_stats") or {}).get(args.agent, {})
    if agent_stats:
        print(f"\nMessage statuses:")
        for k, v in sorted((agent_stats.get("statuses") or {}).items()):
            print(f"  {k}: {v}")
        print(f"avg_response: {agent_stats.get('avg_response_seconds', 0):.1f}s  total: {agent_stats.get('total', 0)}")

    return 0

if __name__ == "__main__":
    exit(main())
