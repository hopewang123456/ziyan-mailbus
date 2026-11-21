"""MCP 拉取通道：事件先落到 pull 目录，agent 主动拉取后清空。

指名事件读取即删；广播事件保留在 ``broadcast`` 目录，按接收人记录已读
游标，既保证每个接收人至少能拉到一次，也避免同一广播被反复拉取。
"""

from __future__ import annotations

import json
from pathlib import Path

from mailbus.adapters.transport.staging import recipient_of, safe_name, stage_event
from mailbus.core.shared.events import DeliveryResult, OutboxEvent

_BROADCAST = "broadcast"
_BROADCAST_KEEP = 200
_SEEN_DIR = ".seen"


class McpPullTransport:
    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def send(self, event: OutboxEvent) -> DeliveryResult:
        stage_event(self._base / "pull" / recipient_of(event), event)
        return DeliveryResult(ok=True, detail="mcp_staged")

    def drain(self, recipient_id: str) -> list[dict]:
        items = self._drain_personal(recipient_id)
        items.extend(self._drain_broadcast(recipient_id))
        return items

    def _drain_personal(self, recipient_id: str) -> list[dict]:
        folder = self._base / "pull" / safe_name(recipient_id)
        if not folder.is_dir():
            return []
        items: list[dict] = []
        for path in sorted(folder.glob("*.json")):
            payload = _read_json(path)
            if payload is None:
                continue
            path.unlink(missing_ok=True)
            items.append(payload)
        return items

    def _drain_broadcast(self, recipient_id: str) -> list[dict]:
        folder = self._base / "pull" / _BROADCAST
        if not folder.is_dir():
            return []
        seen_path = self._base / "pull" / _SEEN_DIR / f"{safe_name(recipient_id)}.json"
        seen = _read_seen(seen_path)
        items: list[dict] = []
        for path in sorted(folder.glob("*.json")):
            if path.stem in seen:
                continue
            payload = _read_json(path)
            if payload is None:
                continue
            seen.add(path.stem)
            items.append(payload)
        _trim(folder, _BROADCAST_KEEP)
        alive = {path.stem for path in folder.glob("*.json")}
        seen &= alive
        if items or seen_path.exists():
            _write_seen(seen_path, seen)
        return items


def _read_json(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_seen(path: Path) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(payload, list):
        return set()
    return {str(item) for item in payload if isinstance(item, str)}


def _write_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")


def _trim(folder: Path, keep: int) -> None:
    paths = sorted(
        folder.glob("*.json"), key=lambda item: (item.stat().st_mtime, item.name)
    )
    for path in paths[:-keep] if len(paths) > keep else []:
        path.unlink(missing_ok=True)
