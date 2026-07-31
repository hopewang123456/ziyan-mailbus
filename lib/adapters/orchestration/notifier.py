"""Minimal NotifierPort — append JSONL + optional stdout."""
from __future__ import annotations

import json
import os
from typing import Any, Mapping

from lib.utils import _now_iso


class FileNotifier:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def _path(self) -> str:
        return os.path.join(self.data_dir, "system", "notifications.jsonl")

    def notify(self, event: str, payload: Mapping[str, Any] | None = None) -> None:
        row = {"ts": _now_iso(), "event": event, "payload": dict(payload or {})}
        path = self._path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
