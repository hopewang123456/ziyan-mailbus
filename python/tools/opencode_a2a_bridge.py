#!/usr/bin/env python3
"""OpenCode ↔ Mailbus A2A 桥。

OpenCode 容器本体未运行（仅 tail -f /dev/null），通过
`docker exec -w /tmp opencode run <prompt> -m <model> --format json` 执行，
从 NDJSON 事件流拼接 type=text 的 part.text 作为结果。
公共骨架见 a2a_bridge_base.py。

环境变量：
  MAILBUS_API_URL / MAILBUS_AGENTS_FILE / BRIDGE_ENDPOINT / BRIDGE_PORT /
  HEARTBEAT_INTERVAL_SEC 见基类
  OPENCODE_CONTAINER     默认 docker-agents-opencode-1
  OPENCODE_MODEL         默认 deepseek/deepseek-v4-pro
  OPENCODE_TIMEOUT_SEC   默认 300
"""

from __future__ import annotations

import json
import os
import subprocess

from a2a_bridge_base import BridgeBase


class OpencodeBridge(BridgeBase):
    SERVICE = "opencode-a2a-bridge"
    HB_PREFIX = "opencode"
    DEFAULT_PORT = 9915
    DEFAULT_ENDPOINT = "http://172.28.0.1:9915/"

    def __init__(self) -> None:
        super().__init__()
        self.container = os.environ.get("OPENCODE_CONTAINER", "docker-agents-opencode-1")
        self.model = os.environ.get("OPENCODE_MODEL", "deepseek/deepseek-v4-pro")
        self.timeout = float(os.environ.get("OPENCODE_TIMEOUT_SEC", "300"))

    def run(self, agent: dict, text: str) -> tuple[bool, str]:
        try:
            proc = subprocess.run(
                ["docker", "exec", "-w", "/tmp", self.container, "opencode", "run", text,
                 "-m", self.model, "--format", "json"],
                capture_output=True, text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return False, f"OpenCode 超时（>{self.timeout:.0f}s）"
        except Exception as exc:  # noqa: BLE001 - docker 不可用
            return False, f"{type(exc).__name__}: {exc}"
        parts: list[str] = []
        err_msg = ""
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001 - 跳过非 JSON 行
                continue
            if obj.get("type") == "text":
                part = obj.get("part") or {}
                if part.get("type") == "text" and part.get("text"):
                    parts.append(str(part["text"]))
            elif obj.get("type") == "error":
                err = (obj.get("error") or {}).get("data") or {}
                err_msg = str(err.get("message") or obj.get("error"))
        result = "".join(parts).strip()
        if not result:
            return False, (
                f"无 text 事件（exit {proc.returncode}）: "
                f"{err_msg or (proc.stderr or '')[-300:]}"
            )
        return True, result[:8000]


if __name__ == "__main__":
    OpencodeBridge().serve()
