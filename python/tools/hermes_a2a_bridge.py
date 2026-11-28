#!/usr/bin/env python3
"""Hermes ↔ Mailbus A2A 桥。

Mailbus 出站 A2A 是「POST 事件文档」，而 Hermes 9900 只接受 A2A JSON-RPC
(`message/send`)。本桥把两者接通，公共骨架见 a2a_bridge_base.py。

环境变量：
  MAILBUS_API_URL / MAILBUS_AGENTS_FILE / BRIDGE_ENDPOINT / BRIDGE_PORT /
  HEARTBEAT_INTERVAL_SEC 见基类
  HERMES_A2A_BASE    默认 http://hermes:9900
  HERMES_A2A_TOKEN   Hermes A2A Bearer（默认读 A2A_BEARER_TOKEN）
  HERMES_TIMEOUT_SEC 默认 120
"""

from __future__ import annotations

import os
import time

from a2a_bridge_base import BridgeBase


def _extract_text(result: dict) -> list[str]:
    texts: list[str] = []
    status_obj = result.get("status") or {}
    message = status_obj.get("message") or {}
    for part in message.get("parts") or []:
        if part.get("text"):
            texts.append(str(part["text"]))
    for artifact in result.get("artifacts") or []:
        for part in artifact.get("parts") or []:
            if part.get("text"):
                texts.append(str(part["text"]))
    return texts


class HermesBridge(BridgeBase):
    SERVICE = "hermes-a2a-bridge"
    HB_PREFIX = "hermes"
    DEFAULT_PORT = 9910
    DEFAULT_ENDPOINT = "http://172.28.0.1:9910/"
    REQUIRED_KEYS = ("token", "profile")
    ALIAS_KEYS = ("profile",)
    PROMPT_NODE_ID = True

    def __init__(self) -> None:
        super().__init__()
        self.hermes_base = os.environ.get("HERMES_A2A_BASE", "http://hermes:9900").rstrip("/")
        self.hermes_token = (
            os.environ.get("HERMES_A2A_TOKEN") or os.environ.get("A2A_BEARER_TOKEN") or ""
        )
        self.timeout = float(os.environ.get("HERMES_TIMEOUT_SEC", "120"))

    def label(self, agent: dict) -> str:
        return str(agent.get("profile") or agent.get("name") or "?")

    def heartbeat_message_id(self, agent: dict) -> str:
        return f"hb-{agent.get('profile')}-{int(time.time())}"

    def run(self, agent: dict, text: str) -> tuple[bool, str]:
        payload = {
            "jsonrpc": "2.0",
            "id": f"mb-{int(time.time() * 1000)}",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "messageId": f"msg-{int(time.time() * 1000)}",
                    "parts": [{"kind": "text", "text": text}],
                }
            },
        }
        try:
            status, data = self.post_json(
                f"{self.hermes_base}/{agent['profile']}",
                payload,
                self.hermes_token,
                self.timeout,
            )
        except Exception as exc:  # noqa: BLE001 - 网络/超时
            return False, f"{type(exc).__name__}: {exc}"
        if status != 200 or not isinstance(data, dict):
            return False, f"HTTP {status}"
        if data.get("error"):
            return False, str(data["error"].get("message") or data["error"])
        result = data.get("result") or {}
        texts = _extract_text(result)
        state = str((result.get("status") or {}).get("state") or "")
        ok = "COMPLETED" in state or bool(texts)
        return ok, ("\n".join(texts) if texts else state)


if __name__ == "__main__":
    HermesBridge().serve()
