"""Runtime Harness — agent 进程生命周期（stub / production / record / replay）。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from lib.infra.constants import MAILBUS_ROOT


@dataclass
class HarnessSession:
    session_id: str
    agent_id: str
    framework: str = ""
    transport_channel: str = "file_bus"
    data_dir: str = ""
    task_id: str = ""
    step_id: str = ""
    msg_id: str = ""


@dataclass
class HarnessOutcome:
    ok: bool
    ack_received: bool = False
    step_result: Optional[dict] = None
    error: Optional[str] = None
    cli_pid: Optional[int] = None


class AgentHarness:
    def spawn(self, agent_id: str, payload: dict) -> HarnessSession:
        raise NotImplementedError

    def wait_completion(self, session: HarnessSession, timeout: int = 300) -> HarnessOutcome:
        raise NotImplementedError

    def cancel(self, session: HarnessSession) -> None:
        pass

    def health(self, agent_id: str) -> dict:
        return {"ok": True, "agent_id": agent_id}

    def reconcile(self, data_dir: str) -> list[dict]:
        """薄包装 execution_orchestrator.run_orchestrator(mode=light)。"""
        from lib.application.orchestration.execution import run_orchestrator
        from lib.infra.utils import json_read

        cfg = json_read(os.path.join(data_dir, "config.json"), {})
        agents = cfg.get("agents") or {}
        report = run_orchestrator(data_dir, agents, fix=True, mode="light")
        return report.get("anomalies") or []


def _resolve_fixtures_dir(cfg: dict) -> str:
    fixtures = (
        cfg.get("replay_fixtures_dir")
        or cfg.get("stub_fixtures_dir")
        or "tests/fixtures/harness_stub"
    )
    root = str(MAILBUS_ROOT)
    if not os.path.isabs(fixtures):
        fixtures = os.path.join(root, fixtures)
    return fixtures


def resolve_harness_rules_path(
    config: Optional[dict] = None,
    *,
    data_dir: str = "",
) -> str:
    """Absolute rules SoT path from config.harness.rules_path, else MAILBUS_RULES_ROOT."""
    cfg = (config or {}).get("harness") or {}
    raw = str(cfg.get("rules_path") or "").strip()
    if not raw and data_dir:
        from lib.infra.utils import json_read

        store_cfg = json_read(os.path.join(data_dir, "config.json"), {})
        raw = str(((store_cfg.get("harness") or {}).get("rules_path")) or "").strip()
    if raw:
        return raw if os.path.isabs(raw) else os.path.join(str(MAILBUS_ROOT), raw)
    from lib.infra.constants import MAILBUS_RULES_ROOT

    return str(MAILBUS_RULES_ROOT)


def get_harness(config: Optional[dict] = None) -> AgentHarness:
    cfg = (config or {}).get("harness") or {}
    mode = cfg.get("mode", "production")
    if mode == "stub":
        from tests.harness_fixtures.stub import StubHarness

        return StubHarness(_resolve_fixtures_dir(cfg))
    if mode == "replay":
        from tests.harness_fixtures.replay import ReplayHarness

        return ReplayHarness(_resolve_fixtures_dir(cfg))
    if mode == "record":
        from tests.harness_fixtures.record import RecordHarness

        record_dir = cfg.get("record_dir") or os.path.join(str(MAILBUS_ROOT), "store", "harness-recordings")
        if not os.path.isabs(record_dir):
            record_dir = os.path.join(str(MAILBUS_ROOT), record_dir)
        return RecordHarness(record_dir=record_dir)
    from .production import ProductionHarness

    return ProductionHarness()


from .contract import HarnessContract, build_contract, write_d1_step_result  # noqa: E402
