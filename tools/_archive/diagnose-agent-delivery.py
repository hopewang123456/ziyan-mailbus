#!/usr/bin/env python3
"""诊断指定 agent 在 pipeline 上的推送/回复/落盘问题。"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.api_stall_detect import detect_api_stall, read_reply_text_for_agent
from lib.agent_adapters import agent_cli_active_for, resolve_container, get_adapter
from lib.docker_probe import docker_exec_ps
from lib.models import Inbox
from lib.utils import json_read, resolve_paths


def diagnose(data_dir: str, agent: str, task_id: str) -> dict:
    config = json_read(os.path.join(data_dir, "config.json"), {})
    agents_cfg = config.get("agents") or {}
    ac = agents_cfg.get(agent) or {}
    paths = resolve_paths(data_dir)

    report: dict = {
        "agent": agent,
        "task_id": task_id,
        "type": ac.get("type"),
        "model": ac.get("model"),
        "issues": [],
        "inbox_msgs": [],
    }

    # inbox
    ib = Inbox.from_dict(json_read(os.path.join(paths["inbox"], agent, "inbox.json"), {}))
    for m in ib.messages:
        c = ib.msg_field(m, "content", "") or ""
        if task_id not in c:
            continue
        mid = ib.msg_field(m, "id", "")
        entry = {
            "msg_id": mid,
            "state": ib.msg_field(m, "state", ""),
            "pushed_count": ib.msg_field(m, "pushed_count", 0),
            "last_pushed_at": ib.msg_field(m, "last_pushed_at", ""),
            "api_stall_reason": ib.msg_field(m, "api_stall_reason", ""),
            "failover_tried": ib.msg_field(m, "failover_tried", ""),
        }
        report["inbox_msgs"].append(entry)
        reply = read_reply_text_for_agent(data_dir, agent, mid)
        entry["reply_len"] = len(reply)
        stall = detect_api_stall(reply)
        if stall:
            entry["api_stall_detected"] = stall
            report["issues"].append(f"reply 含 API/网络错误: {stall}")
        if not reply and entry["state"] in ("processing", "done"):
            report["issues"].append(f"msg {mid}: 无 reply 文本（静默失败典型）")

    # codex container
    if ac.get("type") == "codex":
        adapter = get_adapter("codex")
        svc = (ac.get("docker") or {}).get("service") or agent
        container = resolve_container(ac, agent, svc)
        report["docker_container"] = container
        ps = docker_exec_ps(container)
        report["codex_exec_lines"] = sum(1 for ln in ps.splitlines() if "codex exec" in ln)
        if "bwrap" in (read_reply_text_for_agent(data_dir, agent, "") or ""):
            pass
        reply_all = read_reply_text_for_agent(data_dir, agent, "")
        if "bwrap" in reply_all:
            report["issues"].append("历史 reply 含 bwrap 沙箱失败（WSL 无 user namespace）")
        wrong = resolve_container(ac, agent, adapter.container_service if adapter else "")
        if wrong != container:
            report["issues"].append(
                f"曾用默认容器 {wrong} 检测 CLI，应用 {container}（已修 agent_cli_active_for）"
            )

    report["cli_active"] = agent_cli_active_for(
        agent, agents_cfg, msg_id=(report["inbox_msgs"][-1]["msg_id"] if report["inbox_msgs"] else ""),
        task_id=task_id,
    )

    rp = os.path.join(data_dir, "replies", f"{agent}.json")
    if os.path.isfile(rp):
        raw = json_read(rp, {})
        report["last_reply_msg_ids"] = raw.get("msg_ids")
        report["last_reply_ts"] = raw.get("timestamp")
        body = (raw.get("reply") or "")[:500]
        if "ParserError" in body or "PowerShell" in body:
            report["issues"].append("reply 含 PowerShell ParserError（Windows 推送路径问题）")

    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Diagnose agent delivery issues")
    p.add_argument("--agent", required=True)
    p.add_argument("--task-id", default="game-courier-20260625")
    p.add_argument("--out", default="")
    args = p.parse_args()
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store")
    rep = diagnose(data_dir, args.agent, args.task_id)
    text = json.dumps(rep, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"written {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
