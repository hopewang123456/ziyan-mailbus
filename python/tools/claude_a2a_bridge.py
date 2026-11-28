#!/usr/bin/env python3
"""Claude Code ↔ Mailbus A2A 桥。

在宿主直接编排 `claude -p`（print 模式），通过 CLAUDE_CONFIG_DIR 区分不同
agent 的身份/密钥/模型配置，从 stream-json 取结果。
公共骨架见 a2a_bridge_base.py。

环境变量：
  MAILBUS_API_URL / MAILBUS_AGENTS_FILE / BRIDGE_ENDPOINT / BRIDGE_PORT /
  HEARTBEAT_INTERVAL_SEC 见基类
  CLAUDE_TIMEOUT_SEC     默认 420
"""

from __future__ import annotations

import json
import os
import subprocess

from a2a_bridge_base import BridgeBase


class ClaudeBridge(BridgeBase):
    SERVICE = "claude-a2a-bridge"
    HB_PREFIX = "claude"
    DEFAULT_PORT = 9914
    DEFAULT_ENDPOINT = "http://172.28.0.1:9914/"
    REQUIRED_KEYS = ("token", "config_dir")

    def __init__(self) -> None:
        super().__init__()
        self.timeout = float(os.environ.get("CLAUDE_TIMEOUT_SEC", "420"))

    def run(self, agent: dict, text: str) -> tuple[bool, str]:
        env = os.environ.copy()
        env["CLAUDE_CONFIG_DIR"] = agent["config_dir"]
        env.setdefault("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")
        try:
            proc = subprocess.run(
                ["claude", "-p", text, "--verbose", "--output-format", "stream-json"],
                env=env, capture_output=True, text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return False, f"Claude 超时（>{self.timeout:.0f}s）"
        except Exception as exc:  # noqa: BLE001 - CLI 不可用
            return False, f"{type(exc).__name__}: {exc}"
        result = ""
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001 - 跳过非 JSON 行
                continue
            if obj.get("type") == "result" and obj.get("result"):
                result = str(obj["result"])
            elif obj.get("type") == "assistant":
                msg = obj.get("message") or {}
                for block in (msg.get("content") or []):
                    if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                        result = str(block["text"])
        if not result:
            err = (proc.stderr or proc.stdout or "").strip()
            return False, f"无 result（exit {proc.returncode}）: {err[-400:]}"
        return True, result[:8000]


if __name__ == "__main__":
    ClaudeBridge().serve()
