#!/usr/bin/env python3
"""
mailbus → AgentMemory 桥接脚本
每次 mailbus scan 后运行，将已 ack 且未同步的消息写入 AgentMemory。
保证每个 agent 重启后能通过 AgentMemory 检索到历史消息。

用法: python3 mailbus-memory-bridge.py --data-dir /mnt/e/ai_tools/mail/store

运行条件：
- AgentMemory 在 http://localhost:3111 运行
- mailbus store 目录可读
"""
import json
import os
import sys
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path

AGENTMEMORY_URL = "http://localhost:3111"

# 已同步的消息 ID 记录文件（跟 inbox 同级，避免重复写入记忆）
SYNC_MARKER_FILE = "sync_to_memory.json"


def get_inboxes(data_dir: str) -> list[dict]:
    """扫描所有 agent 的 inbox，返回未同步的已 ack 消息"""
    inbox_dir = Path(data_dir) / "inbox"
    if not inbox_dir.exists():
        return []

    results = []
    for agent_dir in sorted(inbox_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_name = agent_dir.name
        inbox_file = agent_dir / "inbox.json"
        sync_marker = agent_dir / SYNC_MARKER_FILE

        if not inbox_file.exists():
            continue

        with open(inbox_file, "r", encoding="utf-8") as f:
            inbox_data = json.load(f)

        # 读取已同步记录
        synced_ids = set()
        if sync_marker.exists():
            try:
                with open(sync_marker, "r", encoding="utf-8") as f:
                    synced_ids = set(json.load(f))
            except (json.JSONDecodeError, KeyError):
                synced_ids = set()

        for msg in inbox_data.get("messages", []):
            msg_id = msg.get("id", "")
            status = msg.get("status", "")
            content = msg.get("content", "")
            from_agent = msg.get("from", "unknown")

            # 只同步已 ack 且未同步过的消息（非系统测试消息）
            if status != "acknowledged":
                continue
            if msg_id in synced_ids:
                continue
            if not content.strip():
                continue
            # 跳过纯测试消息（如写入文件测试）
            if "写入" in content and ".txt" in content:
                continue

            results.append({
                "agent": agent_name,
                "msg_id": msg_id,
                "from": from_agent,
                "content": content,
                "type": msg.get("type", "notice"),
                "created_at": msg.get("created_at", ""),
            })

        # 保存已同步 ID（等全部成功后再更新）
        results.append({
            "_save_sync": True,
            "_agent": agent_name,
            "_synced_ids": synced_ids,
            "_pending_ids": [m["msg_id"] for m in results if m.get("agent") == agent_name and "_save_sync" not in m],
        })

    return results


def get_agentmemory_health() -> dict:
    """GET 健康检查"""
    url = f"{AGENTMEMORY_URL}/agentmemory/health"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}: {body}"}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e.reason}"}


def post_to_agentmemory(endpoint: str, payload: dict) -> dict:
    """POST 到 AgentMemory REST API"""
    url = f"{AGENTMEMORY_URL}{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}: {body}"}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e.reason}"}


def write_memory_to_agentmemory(agent: str, msg_id: str, content: str, from_agent: str, msg_type: str):
    """将一条消息写入 AgentMemory，按 agent 分类"""
    # 先查这个 agent 的已有记忆，避免重复过多
    title = f"[mailbus] {from_agent} → {agent}"
    # 给内容添加 agent 标签方便检索
    tagged_content = f"[agent:{agent}] [from:{from_agent}] [msg_id:{msg_id}] {content}"

    payload = {
        "content": tagged_content,
        "metadata": {
            "source": f"mailbus-{agent}",
            "from": from_agent,
            "to": agent,
            "msg_id": msg_id,
            "type": msg_type,
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }
    return post_to_agentmemory("/agentmemory/remember", payload)


def main():
    parser = argparse.ArgumentParser(description="Sync mailbus messages to AgentMemory")
    parser.add_argument("--data-dir", required=True, help="mailbus data directory")
    args = parser.parse_args()

    # 先检查 AgentMemory 是否可用
    # health 是 GET 请求
    health = get_agentmemory_health()
    if health.get("error") or health.get("status") != "healthy":
        # AgentMemory 不可用时不阻塞 mailbus scan
        print("[memory-bridge] AgentMemory 不可用，跳过同步")
        return

    messages = get_inboxes(args.data_dir)

    # 分离同步指令和实际消息
    sync_ops = [m for m in messages if "_save_sync" in m]
    actual_msgs = [m for m in messages if "_save_sync" not in m]

    if not actual_msgs:
        print("[memory-bridge] 无新消息需要同步")
        return

    print(f"[memory-bridge] 开始同步 {len(actual_msgs)} 条消息到 AgentMemory...")

    success_count = 0
    fail_count = 0
    # 按 agent 分组写入
    for msg in actual_msgs:
        result = write_memory_to_agentmemory(
            agent=msg["agent"],
            msg_id=msg["msg_id"],
            content=msg["content"],
            from_agent=msg["from"],
            msg_type=msg["type"],
        )
        if result.get("success") or result.get("memory"):
            success_count += 1
        else:
            print(f"  [WARN] 同步失败 {msg['msg_id']}: {result.get('error', 'unknown')}")
            fail_count += 1

    # 更新同步标记文件
    for op in sync_ops:
        agent = op["_agent"]
        synced = op["_synced_ids"]
        pending = op["_pending_ids"]
        if success_count > 0:
            # 只把成功的标记为已同步
            synced.update(pending)
            sync_file = Path(args.data_dir) / "inbox" / agent / SYNC_MARKER_FILE
            with open(sync_file, "w", encoding="utf-8") as f:
                json.dump(sorted(synced), f, ensure_ascii=False)

    print(f"[memory-bridge] 完成: {success_count} 成功{f', {fail_count} 失败' if fail_count else ''}")


if __name__ == "__main__":
    main()
