#!/usr/bin/env python3
"""将团队规范同步到：公告板 + team-memory.db + AgentMemory（best-effort）+ 各 agent notice。

用法:
  python3 tools/tools/ops/sync-team-rules.py --data-dir store
  python3 tools/tools/ops/sync-team-rules.py --data-dir store --no-notice
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.utils import json_read, json_write, _now_iso
from lib.team_memory_store import store_memory
from lib.agentmemory_config import agentmemory_url, pending_dir as am_pending_dir
from lib.sync_layers import mirror_rules_to_store
from lib.constants import MAILBUS_ROOT

AGENTMEMORY_URL = os.environ.get(
    "AGENTMEMORY_URL",
    agentmemory_url(),
)

RULE_FILES = [
    ("team-secrets-policy", "团队密钥与 sudo 规范"),
    ("execution-order", "执行顺序与并发规范"),
    ("iteration-protocol", "三轮迭代协议"),
]

NOTICE_SUMMARY = """【团队规范已更新】请阅读 store/rules/ 下最新规范：

1. team-secrets-policy.md — .env.secrets 禁止提交 git，sudo 密码不得写入代码/记忆
2. execution-order.md — 主任务优先、每 agent 串行、Round2 门禁、light 编排器
3. iteration-protocol.md — Round1→audit→Round2 流程

运维：docker-agents/.env.secrets（gitignore）+ wsl-sudo.sh
排查：python3 tools/pipeline-watchdog.py --data-dir store
"""


def _read_rule(data_dir: str, stem: str) -> str:
    path = os.path.join(data_dir, "rules", f"{stem}.md")
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def _post_json(url: str, payload: dict, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except TimeoutError:
        raise
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode("utf-8", errors="replace")}
    except urllib.error.URLError as e:
        return {"error": str(e.reason)}


def _remember_payload(agent: str, title: str, content: str, rule_id: str) -> dict:
    tagged = f"[team-rule:{rule_id}] [scope:all-agents] {title}\n\n{content[:8000]}"
    return {
        "content": tagged,
        "metadata": {
            "source": f"mailbus-team-rules-{agent}",
            "rule_id": rule_id,
            "scope": "team",
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }


def _remember(agent: str, title: str, content: str, rule_id: str) -> bool:
    payload = _remember_payload(agent, title, content, rule_id)
    try:
        r = _post_json(f"{AGENTMEMORY_URL}/agentmemory/remember", payload, timeout=8)
    except Exception as exc:
        print(f"  memory timeout {agent}/{rule_id}: {exc}")
        return False
    ok = bool(r.get("success") or r.get("memory")) and not r.get("error")
    if not ok and r.get("error"):
        print(f"  memory fail {agent}/{rule_id}: {r.get('error')[:120]}")
    return ok


def sync_bulletin(data_dir: str, title: str, content: str) -> None:
    bulletin_file = os.path.join(data_dir, "bulletin.json")
    data = json_read(bulletin_file, {"bulletins": []})
    entry = {
        "id": f"bulletin-team-rules-{_now_iso()[:10]}",
        "from": "mailbus",
        "from_name": "mailbus",
        "title": title,
        "content": content[:4000],
        "created_at": _now_iso(),
    }
    # 去重：同日同标题只保留最新
    data["bulletins"] = [
        b for b in data.get("bulletins", [])
        if b.get("id") != entry["id"]
    ]
    data["bulletins"].insert(0, entry)
    json_write(bulletin_file, data)
    print(f"  bulletin: {entry['id']}")


def sync_team_memory(data_dir: str) -> int:
    """团队规范写入 team-memory.db（不依赖 AgentMemory）。"""
    ok = 0
    for stem, title in RULE_FILES:
        body = _read_rule(data_dir, stem)
        if not body:
            continue
        key = f"team-rule:{stem}"
        tagged = f"[team-rule:{stem}] [scope:all-agents] {title}\n\n{body[:8000]}"
        if store_memory(key, tagged, category="decision", author="mailbus"):
            ok += 1
            print(f"  team-memory: {stem}")
    return ok


def sync_agentmemory(agents: list[str], data_dir: str) -> int:
    try:
        with urllib.request.urlopen(f"{AGENTMEMORY_URL}/agentmemory/health", timeout=5) as r:
            health = json.loads(r.read())
    except Exception:
        try:
            with urllib.request.urlopen(f"{AGENTMEMORY_URL}/health", timeout=5) as r:
                health = json.loads(r.read())
        except Exception as exc:
            print(f"  AgentMemory 不可用: {exc}")
            return 0
    if health.get("error"):
        print(f"  AgentMemory 不可用: {health.get('error')}")
        return 0

    ok = 0
    memory_ok = None  # None=unknown, True/False after first write attempt
    for stem, title in RULE_FILES:
        body = _read_rule(data_dir, stem)
        if not body:
            continue
        for agent in agents:
            if memory_ok is False:
                break
            if _remember(agent, title, body, stem):
                ok += 1
                memory_ok = True
                print(f"  memory: {agent} ← {stem}")
            elif memory_ok is None:
                memory_ok = False
                for stem2, title2 in RULE_FILES:
                    body2 = _read_rule(data_dir, stem2)
                    if not body2:
                        continue
                    for a2 in agents:
                        queue_agentmemory_pending(
                            data_dir, a2, _remember_payload(a2, title2, body2, stem2), stem2,
                        )
                print("  AgentMemory remember 不可用，已入队 agentmemory-pending（memory_bridge 会重试）")
                break
        if memory_ok is False:
            break
    return ok


def queue_agentmemory_pending(data_dir: str, agent: str, payload: dict, rule_id: str) -> None:
    pending_root = am_pending_dir(data_dir)
    pending_root.mkdir(parents=True, exist_ok=True)
    fname = f"{rule_id}-{agent}.json"
    json_write(str(pending_root / fname), {"agent": agent, "rule_id": rule_id, "payload": payload})


def send_notices(data_dir: str, agents: list[str]) -> int:
    from lib.commands import cmd_send

    n = 0
    for name in agents:
        class Args:
            pass

        a = Args()
        a.data_dir = data_dir
        a.agent = name
        a.from_ = "mailbus"
        a.type = "notice"
        a.priority = "normal"
        a.msg = NOTICE_SUMMARY
        a.domain = ""
        a.project = ""
        try:
            if cmd_send(a) == 0:
                n += 1
        except Exception as exc:
            print(f"  notice {name} failed: {exc}")
    return n


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=os.environ.get("MAILBUS_DATA", "store"))
    parser.add_argument("--no-notice", action="store_true", help="不发送 inbox notice")
    parser.add_argument("--no-memory", action="store_true", help="不写 AgentMemory")
    parser.add_argument("--no-sqlite", action="store_true", help="不写 team-memory.db")
    args = parser.parse_args()

    config = json_read(os.path.join(args.data_dir, "config.json"), {})
    agents = list(config.get("agents", {}).keys())
    if not agents:
        print("无 agent 配置")
        return 1

    print("=== sync team rules ===")
    mirrored = mirror_rules_to_store(args.data_dir, mail_root=MAILBUS_ROOT)
    print(f"  rules mirror: mail/rules → store/rules ({len(mirrored)} files)")
    combined = NOTICE_SUMMARY + "\n\n详见 store/rules/*.md"
    sync_bulletin(args.data_dir, "📢 团队规范：密钥安全 + 执行顺序", combined)

    if not args.no_sqlite:
        nsql = sync_team_memory(args.data_dir)
        if nsql == 0:
            print("  team-memory 写入失败或 rules 为空")

    if not args.no_memory:
        nmem = sync_agentmemory(agents, args.data_dir)
        if nmem == 0:
            print("  AgentMemory 写入失败或不可用（best-effort）；规范已写入 bulletin + team-memory")

    if not args.no_notice:
        n = send_notices(args.data_dir, agents)
        print(f"  notices sent: {n}/{len(agents)}")

    print("=== done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
