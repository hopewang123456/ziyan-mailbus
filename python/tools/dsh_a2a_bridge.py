#!/usr/bin/env python3
"""DSH ↔ Mailbus A2A 桥。

DSH 没有 HTTP A2A 入口，只能通过
`docker exec <container> dsh --profile <profile> '<task>'` 执行并从 stdout 取结果。
公共骨架见 a2a_bridge_base.py。

环境变量：
  MAILBUS_API_URL / MAILBUS_AGENTS_FILE / BRIDGE_ENDPOINT / BRIDGE_PORT /
  HEARTBEAT_INTERVAL_SEC 见基类
  DSH_CONTAINER          默认 mailbus-dsh
  DSH_PROFILE            默认 headless
  DSH_TIMEOUT_SEC        默认 300
"""

from __future__ import annotations

import os
import subprocess

from a2a_bridge_base import BridgeBase


class DshBridge(BridgeBase):
    SERVICE = "dsh-a2a-bridge"
    HB_PREFIX = "dsh"
    DEFAULT_PORT = 9911
    DEFAULT_ENDPOINT = "http://172.28.0.1:9911/"

    def __init__(self) -> None:
        super().__init__()
        self.container = os.environ.get("DSH_CONTAINER", "mailbus-dsh")
        self.profile = os.environ.get("DSH_PROFILE", "headless")
        self.timeout = float(os.environ.get("DSH_TIMEOUT_SEC", "300"))

    def run(self, agent: dict, text: str) -> tuple[bool, str]:
        try:
            proc = subprocess.run(
                ["docker", "exec", self.container, "dsh", "--profile", self.profile, text],
                capture_output=True, text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return False, f"DSH 超时（>{self.timeout:.0f}s）"
        except Exception as exc:  # noqa: BLE001 - docker 不可用
            return False, f"{type(exc).__name__}: {exc}"
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0 and not out:
            return False, f"DSH exit {proc.returncode}: {err[:500]}"
        return True, (out or err)[:8000]


if __name__ == "__main__":
    DshBridge().serve()
