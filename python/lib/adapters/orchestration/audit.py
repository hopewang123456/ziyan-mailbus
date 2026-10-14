"""AuditPort adapters (D14) — Noop default; optional JSONL file sink."""
from __future__ import annotations

import json
import os
from typing import Any, Mapping

from lib.infra.utils import _now_iso


class NoopAudit:
    def append(self, event: str, payload: Mapping[str, Any] | None = None) -> None:
        return None


class FileAuditAdapter:
    """Append-only JSONL under store/system/audit.jsonl."""

    def __init__(self, data_dir: str, *, filename: str = "audit.jsonl") -> None:
        self._path = os.path.join(data_dir, "system", filename)

    def append(self, event: str, payload: Mapping[str, Any] | None = None) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        line = {"ts": _now_iso(), "event": event, "payload": dict(payload or {})}
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
