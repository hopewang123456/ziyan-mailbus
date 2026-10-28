"""Runtime Harness — agent 进程生命周期（stub / production / record / replay）。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from lib.infra.constants import MAILBUS_ROOT, PROJECT_ROOT


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
    root = str(PROJECT_ROOT)  # tests/ 随 python 实现树走
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
    """按 ``config.harness.mode`` 装配 harness（L3 登记制，P0c 上提）。

    四实现经 ``lib.interfaces.assembler.register("harness", ...)`` 登记
    （登记在本文件尾部），此处查表实例化；**未知 mode fail-fast** 抛
    AssemblyError——此前拼写错误会静默落 production（W7 期隐患）。
    选择键保持 ``harness.mode``（既有配置零迁移）。
    """
    from lib.interfaces.assembler import resolve_factory

    cfg = (config or {}).get("harness") or {}
    mode = str(cfg.get("mode", "production")).strip()
    factory = resolve_factory("harness", mode)
    return factory({"data_dir": "", "harness_cfg": cfg})


def _build_stub_harness(ctx: dict) -> AgentHarness:
    from .fixtures.stub import StubHarness

    return StubHarness(_resolve_fixtures_dir(ctx.get("harness_cfg") or {}))


def _build_replay_harness(ctx: dict) -> AgentHarness:
    from .fixtures.replay import ReplayHarness

    return ReplayHarness(_resolve_fixtures_dir(ctx.get("harness_cfg") or {}))


def _build_record_harness(ctx: dict) -> AgentHarness:
    from .fixtures.record import RecordHarness

    cfg = ctx.get("harness_cfg") or {}
    record_dir = cfg.get("record_dir") or os.path.join(str(MAILBUS_ROOT), "store", "harness-recordings")
    if not os.path.isabs(record_dir):
        record_dir = os.path.join(str(MAILBUS_ROOT), record_dir)
    return RecordHarness(record_dir=record_dir)


def _build_production_harness(ctx: dict) -> AgentHarness:
    from .production import ProductionHarness

    return ProductionHarness()


from lib.interfaces.assembler import register  # noqa: E402  (登记置于工厂定义后)

register("harness", "stub")(_build_stub_harness)
register("harness", "replay")(_build_replay_harness)
register("harness", "record")(_build_record_harness)
register("harness", "production")(_build_production_harness)


from lib.domain.harness_contract import HarnessContract, build_contract, write_d1_step_result  # noqa: E402
