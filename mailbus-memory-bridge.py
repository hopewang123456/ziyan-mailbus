#!/usr/bin/env python3
"""
mailbus → team-memory.db + AgentMemory 双写桥接脚本
每次 mailbus scan 后运行，将已 ack 且未同步的消息写入共享记忆。

用法: python3 mailbus-memory-bridge.py [--data-dir PATH]

默认 data-dir: $MAILBUS_DATA（见 lib/constants.DEFAULT_DATA_DIR）

环境变量:
  TEAM_MEMORY_DB              SQLite 路径（默认见 lib/team_memory_store.py）
  MEMORY_BRIDGE_SQLITE=1      写 team-memory.db（主存储）
  MEMORY_BRIDGE_AGENTMEMORY=1 写 AgentMemory（可选增强）
  AGENTMEMORY_URL             AgentMemory HTTP 基址
"""
from __future__ import annotations

import argparse
import os
import sys

# 允许从 mail 根目录直接运行
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib.constants import DEFAULT_DATA_DIR  # noqa: E402
from lib.memory_bridge import (  # noqa: E402
    AGENTMEMORY_URL,
    bridge_agentmemory_enabled,
    bridge_sqlite_enabled,
    run_bridge,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync mailbus messages to team memory + AgentMemory")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="mailbus data directory")
    parser.add_argument("--limit", type=int, default=20, help="max messages per run (cron safety)")
    args = parser.parse_args()

    url = os.environ.get("AGENTMEMORY_URL", AGENTMEMORY_URL)
    stats = run_bridge(args.data_dir, limit=args.limit, url=url)

    pending = stats.get("pending_am", 0)
    if pending:
        print(f"[memory-bridge] pending queue: {pending} 条已写入 AgentMemory")

    total_work = (
        stats["sqlite_ok"] + stats["sqlite_fail"] + stats["sqlite_skip"]
        + stats["agentmemory_ok"] + stats["agentmemory_fail"] + stats["agentmemory_skip"]
    )
    if total_work == 0 and pending == 0:
        print("[memory-bridge] 无新消息需要同步")
        return

    parts = []
    if bridge_sqlite_enabled():
        parts.append(
            f"sqlite={stats['sqlite_ok']} ok"
            + (f"/{stats['sqlite_fail']} fail" if stats["sqlite_fail"] else "")
            + (f"/{stats['sqlite_skip']} skip" if stats["sqlite_skip"] else "")
        )
    if bridge_agentmemory_enabled():
        am_part = f"agentmemory={stats['agentmemory_ok']} ok"
        if stats["agentmemory_fail"]:
            am_part += f"/{stats['agentmemory_fail']} fail"
        if stats["agentmemory_skip"]:
            am_part += f"/{stats['agentmemory_skip']} skip(unreachable)"
        parts.append(am_part)

    print(f"[memory-bridge] 完成: {', '.join(parts)}")


if __name__ == "__main__":
    main()
