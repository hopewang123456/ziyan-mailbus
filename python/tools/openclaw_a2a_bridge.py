#!/usr/bin/env python3
"""OpenClaw ↔ Mailbus A2A 桥。

OpenClaw 容器的 gateway 因 session 迁移 / native service 问题无法启动，
但 `openclaw agent --local --agent <profile> --json --message-file ...`
可嵌入式执行（runner=embedded），无需 gateway。本桥通过 docker exec 调用。
公共骨架见 a2a_bridge_base.py。

环境变量：
  MAILBUS_API_URL / MAILBUS_AGENTS_FILE / BRIDGE_ENDPOINT / BRIDGE_PORT /
  HEARTBEAT_INTERVAL_SEC 见基类
  OPENCLAW_CONTAINER     默认 docker-agents-openclaw-1
  OPENCLAW_TIMEOUT_SEC   默认 300
  MAILBUS_HOST_ENV       默认 <repo>/shared/docker-agents/.env（自愈注入 key）
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from a2a_bridge_base import BridgeBase


def _collect_terminal_replies(node, out: list[str]) -> None:
    if isinstance(node, dict):
        reply = node.get("terminalReply")
        if isinstance(reply, dict) and reply.get("text"):
            out.append(str(reply["text"]))
        for value in node.values():
            _collect_terminal_replies(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_terminal_replies(value, out)


class OpenclawBridge(BridgeBase):
    SERVICE = "openclaw-a2a-bridge"
    HB_PREFIX = "openclaw"
    DEFAULT_PORT = 9913
    DEFAULT_ENDPOINT = "http://172.28.0.1:9913/"
    REQUIRED_KEYS = ("token", "profile")

    def __init__(self) -> None:
        super().__init__()
        self.container = os.environ.get("OPENCLAW_CONTAINER", "docker-agents-openclaw-1")
        self.timeout = float(os.environ.get("OPENCLAW_TIMEOUT_SEC", "300"))
        self.host_env_file = Path(os.environ.get(
            "MAILBUS_HOST_ENV", "/mnt/e/ai_tools/mailbus/shared/docker-agents/.env"))

    def _read_host_key(self) -> str:
        try:
            for line in self.host_env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:  # noqa: BLE001 - host .env 可能不存在
            return ""
        return ""

    def _ensure_keys(self) -> None:
        """容器 /tmp/oc-keys.env 重启即丢；缺失时从 host .env 自愈注入（stdin 传值）。"""
        try:
            chk = subprocess.run(
                ["docker", "exec", self.container, "sh", "-c", "test -s /tmp/oc-keys.env"],
                capture_output=True, timeout=10,
            )
            if chk.returncode == 0:
                return
        except Exception:  # noqa: BLE001 - docker 不可用则跳过
            return
        key = self._read_host_key()
        if not key:
            return
        content = (f"export DEEPSEEK_API_KEY={key}\nexport OPENAI_API_KEY={key}\n"
                   f"export GLM_API_KEY={key}\nexport ZHIPU_API_KEY={key}\n")
        try:
            subprocess.run(
                ["docker", "exec", "-i", self.container, "sh", "-c", "cat > /tmp/oc-keys.env"],
                input=content, capture_output=True, text=True, timeout=10,
            )
        except Exception:  # noqa: BLE001 - 注入失败不阻断执行
            return

    def run(self, agent: dict, text: str) -> tuple[bool, str]:
        self._ensure_keys()
        profile = agent["profile"]
        statedir = f"/workspace/data/.openclaw-{profile}"
        script = (
            "cat > /tmp/oc-prompt.txt && . /tmp/oc-keys.env; cd /workspace; "
            f"OPENCLAW_STATE_DIR={statedir} OPENCLAW_CONFIG_PATH={statedir}/openclaw.json "
            "OPENCLAW_NO_RESPAWN=1 CI=1 NO_COLOR=1 NODE_COMPILE_CACHE=/var/tmp/oc-cache "
            f"openclaw --no-color agent --local --agent {profile} --json "
            "--message-file /tmp/oc-prompt.txt"
        )
        try:
            proc = subprocess.run(
                ["docker", "exec", "-i", self.container, "sh", "-c", script],
                input=text, capture_output=True, text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return False, f"OpenClaw 超时（>{self.timeout:.0f}s）"
        except Exception as exc:  # noqa: BLE001 - docker 不可用
            return False, f"{type(exc).__name__}: {exc}"
        out = proc.stdout or ""
        idx = out.find("{")
        if idx >= 0:
            try:
                obj, _ = json.JSONDecoder().raw_decode(out[idx:])
                replies: list[str] = []
                _collect_terminal_replies(obj, replies)
                if replies:
                    return True, replies[-1][:8000]
            except Exception:  # noqa: BLE001 - JSON 解析失败走失败分支
                pass
        err = (proc.stderr or out or "").strip()
        return False, f"无 terminalReply（exit {proc.returncode}）: {err[-400:]}"


if __name__ == "__main__":
    OpenclawBridge().serve()
