"""本地通道共用的落盘工具：按接收人分目录、原子写入。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from mailbus.core.shared.events import OutboxEvent

_SAFE = re.compile(r"[^0-9A-Za-z_.-]+")


def recipient_of(event: OutboxEvent) -> str:
    value = str(event.payload.get("recipient_id") or "").strip()
    if not value:
        return "broadcast"
    # 净化接收人标识，防止路径穿越写出收件目录之外。
    return safe_name(value)


def safe_name(value: str) -> str:
    return _SAFE.sub("_", value) or "unknown"


def event_document(event: OutboxEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "kind": event.kind,
        "payload": dict(event.payload),
        "attempts": event.attempts,
    }


def stage_event(folder: Path, event: OutboxEvent) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{safe_name(event.event_id)}.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(
        json.dumps(event_document(event), ensure_ascii=False), encoding="utf-8"
    )
    os.replace(temp, target)
    return target
