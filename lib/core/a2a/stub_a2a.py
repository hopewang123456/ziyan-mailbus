"""Stub A2A JSON-RPC 客户端 — 读 tests/fixtures/harness_stub/*.json。"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from lib.infra.constants import MAILBUS_ROOT
from .errors import NonRetryableTransportError, RetryableTransportError
from .a2a_mapper import to_a2a_message


class StubA2AClient:
    """按 fixture 模拟 SendMessage / GetTask。"""

    def __init__(self, fixture: dict[str, Any]):
        self.fixture = fixture
        self._send_attempt = 0
        self._poll_index = 0
        self._after_resolve = False
        self.task_id = "stub-a2a-task"

    @classmethod
    def from_name(cls, name: str, *, mail_root: Optional[str] = None) -> "StubA2AClient":
        root = mail_root or str(MAILBUS_ROOT)
        base = os.path.join(root, "tests", "fixtures", "harness_stub")
        path = name if name.endswith(".json") else f"{name}.json"
        if not os.path.isabs(path):
            path = os.path.join(base, path)
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def send_message(self, dispatch: dict[str, Any]) -> dict[str, Any]:
        a2a = self.fixture.get("a2a") or {}
        errors = a2a.get("errors") or []
        if self._send_attempt < len(errors):
            err = errors[self._send_attempt]
            self._send_attempt += 1
            if err in ("timeout", "503", "502", "504", "429"):
                raise RetryableTransportError(str(err), code=str(err))
            if err.startswith("http_"):
                code = int(err.split("_", 1)[1])
                if 400 <= code < 500:
                    raise NonRetryableTransportError(err, code=str(code))
            raise RetryableTransportError(str(err), code=str(err))
        _ = to_a2a_message(dispatch)
        seq = a2a.get("get_task_sequence") or [{"status": "working"}]
        first = seq[0]
        self.task_id = first.get("id") or "a2a-stub-task"
        return {"task": {"id": self.task_id, "status": first.get("status", "working")}}

    def poll_task(self) -> dict[str, Any]:
        a2a = self.fixture.get("a2a") or {}
        if self._after_resolve:
            seq = a2a.get("after_resolve_get_task_sequence") or []
        else:
            seq = a2a.get("get_task_sequence") or [{"status": "completed"}]
        if not seq:
            return {"id": self.task_id, "status": "completed"}
        idx = min(self._poll_index, len(seq) - 1)
        task = dict(seq[idx])
        task.setdefault("id", self.task_id)
        status = (task.get("status") or "").lower()
        if status == "input-required":
            return task
        self._poll_index += 1
        if self._poll_index >= len(seq) and not self._after_resolve:
            return task
        return task

    def mark_resolved(self) -> None:
        self._after_resolve = True
        self._poll_index = 0

    def is_terminal(self, task: dict[str, Any]) -> bool:
        return (task.get("status") or "").lower() in ("completed", "failed", "canceled", "cancelled")
