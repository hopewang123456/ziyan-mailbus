"""Record Harness — 包装 production，录制 spawn/wait 到 JSON。"""
from __future__ import annotations

from lib.adapters.clock import now_dt, now_ts, now_utc_dt
import json
import os
from datetime import datetime, timezone
from typing import Any

from . import AgentHarness, HarnessOutcome, HarnessSession
from .production import ProductionHarness


def _utc_now() -> str:
    return now_utc_dt().replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RecordHarness(AgentHarness):
    def __init__(self, inner: AgentHarness | None = None, record_dir: str = ""):
        self._inner = inner or ProductionHarness()
        self.record_dir = record_dir
        os.makedirs(record_dir, exist_ok=True)

    def _recording_path(self, session: HarnessSession) -> str:
        safe = session.session_id.replace(os.sep, "_")
        return os.path.join(self.record_dir, f"{session.agent_id}-{safe}.json")

    def _write_recording(self, session: HarnessSession, phase: str, payload: dict[str, Any]) -> None:
        path = self._recording_path(session)
        doc: dict[str, Any]
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
        else:
            doc = {
                "schema": "mailbus-harness-record-v1",
                "agent_id": session.agent_id,
                "session_id": session.session_id,
                "events": [],
            }
        doc.setdefault("events", []).append({"phase": phase, "at": _utc_now(), **payload})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def spawn(self, agent_id: str, payload: dict) -> HarnessSession:
        session = self._inner.spawn(agent_id, payload)
        self._write_recording(
            session,
            "spawn",
            {
                "payload": payload,
                "session": {
                    "session_id": session.session_id,
                    "agent_id": session.agent_id,
                    "framework": session.framework,
                    "transport_channel": session.transport_channel,
                    "data_dir": session.data_dir,
                    "task_id": session.task_id,
                    "step_id": session.step_id,
                    "msg_id": session.msg_id,
                },
            },
        )
        return session

    def wait_completion(self, session: HarnessSession, timeout: int = 300) -> HarnessOutcome:
        outcome = self._inner.wait_completion(session, timeout)
        self._write_recording(
            session,
            "wait",
            {
                "timeout": timeout,
                "outcome": {
                    "ok": outcome.ok,
                    "ack_received": outcome.ack_received,
                    "step_result": outcome.step_result,
                    "error": outcome.error,
                    "cli_pid": outcome.cli_pid,
                },
            },
        )
        return outcome

    def cancel(self, session: HarnessSession) -> None:
        self._inner.cancel(session)

    def health(self, agent_id: str) -> dict:
        return self._inner.health(agent_id)
