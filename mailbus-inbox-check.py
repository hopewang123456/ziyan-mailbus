#!/usr/bin/env python3
"""
ziyan-mailbus inbox 检查助手

各 agent 在启动时或收到通知时运行此脚本：
  1. 检查自己的 inbox 是否有未读消息
  2. 如果有，读取并回复 ack
  3. 输出消息摘要供 agent 处理

用法:
  python3 mailbus-inbox-check.py <agent_name> [--ack]

选项:
  --ack    自动回复 ack（标记为 acknowledged）
  --help   查看此帮助
"""

import sys
import os
import json
from datetime import datetime, timezone, timedelta

MAILBUS_DIR = "/mnt/e/ai_tools/mail/store"


def now_iso() -> str:
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S%z")


def check_inbox(agent_name: str, auto_ack: bool = False) -> int:
    """
    检查 agent 的 inbox。
    
    auto_ack=True: 自动回复 ack（标记为 acknowledged）
    
    返回未读消息数。
    """
    inbox_file = f"{MAILBUS_DIR}/inbox/{agent_name}/inbox.json"
    
    if not os.path.exists(inbox_file):
        print(f"[mailbus] inbox 不存在: {inbox_file}")
        return 0
    
    try:
        with open(inbox_file) as f:
            inbox = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        print(f"[mailbus] inbox 读取失败: {inbox_file}")
        return 0
    
    has_unread = inbox.get("has_unread", False)
    messages = inbox.get("messages", [])
    
    # 找出 pending 状态的消息
    pending = [m for m in messages if m.get("status") == "pending"]
    
    if not pending:
        print(f"[mailbus] ✓ {agent_name}: 无未读消息")
        return 0
    
    print(f"[mailbus] 📬 {agent_name}: {len(pending)} 条未读消息:")
    for m in pending:
        content = m.get("content", "")[:60]
        print(f"       [{m['id']}] {m.get('from', '?')} → {content}")
    
    if auto_ack:
        # 回复 ack.json
        ack_file = f"{MAILBUS_DIR}/inbox/{agent_name}/ack.json"
        ack_entries = []
        for m in pending:
            ack_entries.append({
                "action": "ack",
                "msg_id": m["id"],
                "agent": agent_name,
                "timestamp": now_iso(),
            })
        
        # 写入 ack.json（总线读取后清空）
        existing = []
        if os.path.exists(ack_file):
            try:
                with open(ack_file) as f:
                    existing_data = json.load(f)
                    if isinstance(existing_data, list):
                        existing = existing_data
                    elif isinstance(existing_data, dict):
                        existing = [existing_data]
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        
        existing.extend(ack_entries)
        with open(ack_file, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        
        print(f"[mailbus] ✓ 已发送 {len(ack_entries)} 条 ack")
    
    return len(pending)


def main():
    if len(sys.argv) < 2 or "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    
    agent_name = sys.argv[1]
    auto_ack = "--ack" in sys.argv
    
    count = check_inbox(agent_name, auto_ack)
    return 1 if count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
