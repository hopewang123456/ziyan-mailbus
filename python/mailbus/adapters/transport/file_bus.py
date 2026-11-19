"""file_bus 出站：把事件写入本地收件目录，由本地 agent 消费。"""

from __future__ import annotations

from pathlib import Path

from mailbus.adapters.transport.staging import recipient_of, stage_event
from mailbus.core.shared.events import DeliveryResult, OutboxEvent


class FileBusTransport:
    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def send(self, event: OutboxEvent) -> DeliveryResult:
        folder = self._base / "outbox" / recipient_of(event)
        stage_event(folder, event)
        return DeliveryResult(ok=True, detail="file_bus_written")
