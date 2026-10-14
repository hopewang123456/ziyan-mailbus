"""Stub Harness — 读 fixtures 模拟 spawn/wait。"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

from lib.application.harness import AgentHarness, HarnessOutcome, HarnessSession


class StubHarness(AgentHarness):
    def __init__(self, fixtures_dir: str):
        self.fixtures_dir = fixtures_dir

    def load_fixture(self, name: str) -> dict[str, Any]:
        path = name if name.endswith(".json") else f"{name}.json"
        if not os.path.isabs(path):
            path = os.path.join(self.fixtures_dir, path)
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def spawn(self, agent_id: str, payload: dict) -> HarnessSession:
        return HarnessSession(
            session_id=f"stub-{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            transport_channel=payload.get("transport_channel", "file_bus"),
        )

    def wait_completion(self, session: HarnessSession, timeout: int = 300) -> HarnessOutcome:
        fixture_name = session.agent_id
        for candidate in (
            f"path-d-agent-i-opencode.json",
            f"path-a-agent-a-s1.json",
            f"path-b-a2a-fail.json",
        ):
            path = os.path.join(self.fixtures_dir, candidate)
            if os.path.isfile(path):
                data = self.load_fixture(candidate)
                if data.get("agent_id") == session.agent_id:
                    fixture_name = candidate
                    break
        data = self.load_fixture(fixture_name)
        result = data.get("on_complete_step_result")
        return HarnessOutcome(ok=bool(result), ack_received=True, step_result=result)
