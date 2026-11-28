#!/usr/bin/env python3
"""Codex ↔ Mailbus A2A 桥。

通过 `docker exec <container> codex exec --skip-git-repo-check --json '<task>'`
执行，从 NDJSON 输出取最后一条 agent_message.text 作为结果。
公共骨架见 a2a_bridge_base.py。

环境变量：
  MAILBUS_API_URL / MAILBUS_AGENTS_FILE / BRIDGE_ENDPOINT / BRIDGE_PORT /
  HEARTBEAT_INTERVAL_SEC 见基类
  CODEX_TIMEOUT_SEC      默认 300
"""

from __future__ import annotations

import json
import os
import subprocess

from a2a_bridge_base import BridgeBase


class CodexBridge(BridgeBase):
    SERVICE = "codex-a2a-bridge"
    HB_PREFIX = "codex"
    DEFAULT_PORT = 9912
    DEFAULT_ENDPOINT = "http://172.28.0.1:9912/"
    REQUIRED_KEYS = ("token", "container")

    def __init__(self) -> None:
        super().__init__()
        self.timeout = float(os.environ.get("CODEX_TIMEOUT_SEC", "300"))

    def run(self, agent: dict, text: str) -> tuple[bool, str]:
        try:
            proc = subprocess.run(
                ["docker", "exec", agent["container"], "codex", "exec",
                 "--skip-git-repo-check", "--json", text],
                capture_output=True, text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return False, f"Codex 超时（>{self.timeout:.0f}s）"
        except Exception as exc:  # noqa: BLE001 - docker 不可用
            return False, f"{type(exc).__name__}: {exc}"
        last_text = ""
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001 - 跳过非 JSON 行
                continue
            if obj.get("type") == "item.completed":
                item = obj.get("item") or {}
                if item.get("type") == "agent_message" and item.get("text"):
                    last_text = str(item["text"])
        if not last_text:
            err = (proc.stderr or "").strip()
            return False, f"无 agent_message（exit {proc.returncode}）: {err[:300]}"
        return True, last_text[:8000]


if __name__ == "__main__":
    CodexBridge().serve()
