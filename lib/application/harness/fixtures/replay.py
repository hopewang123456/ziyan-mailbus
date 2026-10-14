"""Replay Harness — 读 fixtures 回放 spawn/wait（record 产出物或 harness_stub）。"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

from lib.application.harness import AgentHarness, HarnessOutcome, HarnessSession


class ReplayHarness(AgentHarness):
    def __init__(self, fixtures_dir: str):
        self.fixtures_dir = fixtures_dir

    def load_fixture(self, name: str) -> dict[str, Any]:
        path = name if name.endswith(".json") else f"{name}.json"
        if not os.path.isabs(path):
            path = os.path.join(self.fixtures_dir, path)
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _resolve_fixture(self, session: HarnessSession) -> dict[str, Any]:
        candidates: list[tuple[int, str, dict[str, Any]]] = []
        if os.path.isdir(self.fixtures_dir):
            for name in sorted(os.listdir(self.fixtures_dir)):
                if not name.endswith(".json"):
                    continue
                data = self.load_fixture(name)
                if data.get("agent_id") != session.agent_id:
                    continue
                sr = data.get("on_complete_step_result") or {}
                score = 0
                if session.task_id and sr.get("task_id") == session.task_id:
                    score += 2
                if session.step_id and sr.get("step_id") == session.step_id:
                    score += 2
                candidates.append((score, name, data))
        if candidates:
            candidates.sort(key=lambda item: (-item[0], item[1]))
            return candidates[0][2]

        path = os.path.join(self.fixtures_dir, f"{session.agent_id}.json")
        if os.path.isfile(path):
            return self.load_fixture(session.agent_id)

        raise FileNotFoundError(
            f"no replay fixture for agent_id={session.agent_id!r} under {self.fixtures_dir}"
        )

    def spawn(self, agent_id: str, payload: dict) -> HarnessSession:
        on_spawn = {}
        try:
            data = self._resolve_fixture(
                HarnessSession(
                    session_id="",
                    agent_id=agent_id,
                    task_id=str(payload.get("task_id") or ""),
                    step_id=str(payload.get("step_id") or ""),
                )
            )
            on_spawn = data.get("on_spawn") or {}
        except FileNotFoundError:
            pass
        return HarnessSession(
            session_id=str(on_spawn.get("session_id") or f"replay-{uuid.uuid4().hex[:8]}"),
            agent_id=agent_id,
            framework=str(payload.get("framework") or ""),
            transport_channel=str(
                on_spawn.get("transport_channel")
                or payload.get("transport_channel")
                or "file_bus"
            ),
            data_dir=str(payload.get("data_dir") or ""),
            task_id=str(payload.get("task_id") or ""),
            step_id=str(payload.get("step_id") or ""),
            msg_id=str(payload.get("msg_id") or ""),
        )

    def wait_completion(self, session: HarnessSession, timeout: int = 300) -> HarnessOutcome:
        data = self._resolve_fixture(session)
        on_wait = data.get("on_wait") or {}
        result = data.get("on_complete_step_result") or on_wait.get("step_result")
        ok = on_wait.get("ok", bool(result))
        return HarnessOutcome(
            ok=bool(ok),
            ack_received=bool(on_wait.get("ack_received", True)),
            step_result=result,
            error=on_wait.get("error"),
            cli_pid=on_wait.get("cli_pid"),
        )
