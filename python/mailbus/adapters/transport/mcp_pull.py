"""MCP 拉取通道：事件先落到 pull 目录，agent 主动拉取后清空。"""

from __future__ import annotations

import json
from pathlib import Path

from mailbus.adapters.transport.staging import recipient_of, safe_name, stage_event
from mailbus.core.shared.events import DeliveryResult, OutboxEvent


class McpPullTransport:
    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def send(self, event: OutboxEvent) -> DeliveryResult:
        stage_event(self._base / "pull" / recipient_of(event), event)
        return DeliveryResult(ok=True, detail="mcp_staged")

    def drain(self, recipient_id: str) -> list[dict]:
        folder = self._base / "pull" / safe_name(recipient_id)
        if not folder.is_dir():
            return []
        items: list[dict] = []
        for path in sorted(folder.glob("*.json")):
            try:
                items.append(json.loads(path.read_text(encoding="utf-8")))
            finally:
                path.unlink(missing_ok=True)
        return items
