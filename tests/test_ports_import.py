"""Guard layering: application must not import concrete framework adapters."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "lib"


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                out.append(n.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


class TestLayerImports(unittest.TestCase):
    def test_interfaces_and_domain_import(self):
        from lib.domain import AgentRef, BudgetPaused, Fatal, Retryable
        from lib.interfaces import (
            AgentRuntimePort,
            AuditPort,
            BudgetMeterPort,
            HumanGatePort,
            ResultStorePort,
            TaskFsmPort,
        )

        self.assertTrue(AgentRef)
        self.assertTrue(Fatal)
        self.assertTrue(Retryable)
        self.assertTrue(BudgetPaused)
        self.assertTrue(AgentRuntimePort)
        self.assertTrue(ResultStorePort)
        self.assertTrue(TaskFsmPort)
        self.assertTrue(BudgetMeterPort)
        self.assertTrue(HumanGatePort)
        self.assertTrue(AuditPort)

    def test_application_does_not_import_framework_adapters(self):
        app_dir = ROOT / "application"
        bad_prefix = "lib.adapters.frameworks"
        allow_parts = {"scan", "harness", "push", "ops"}
        offenders: list[str] = []
        for path in app_dir.rglob("*.py"):
            if any(part in allow_parts for part in path.parts):
                continue
            for mod in _imports_of(path):
                if mod.startswith(bad_prefix):
                    offenders.append(f"{path.name}:{mod}")
        self.assertEqual(offenders, [], msg=f"layer violation: {offenders}")

    def test_application_does_not_import_task_fsm(self):
        app_dir = ROOT / "application"
        bad = "lib.adapters.orchestration.task_fsm"
        allow_parts = {"workflow", "scan", "harness", "ops", "orchestration", "integrations", "transport"}
        offenders: list[str] = []
        for path in app_dir.rglob("*.py"):
            if any(part in allow_parts for part in path.parts):
                continue
            for mod in _imports_of(path):
                if mod == bad or mod.startswith(bad + "."):
                    offenders.append(f"{path.relative_to(ROOT)}:{mod}")
        self.assertEqual(offenders, [], msg=f"layer violation: {offenders}")

    def test_adapters_do_not_import_application(self):
        ad_dir = ROOT / "adapters"
        if not ad_dir.is_dir():
            self.skipTest("no adapters yet")
        allow = {
            "task_fsm.py",
            "config_admin.py",
            "init_store.py",
            "doctor_checks.py",
            "heartbeat.py",
            "jobs.py",
            "scheduler.py",
            "human_gate.py",
            "phantom_detect.py",
            "ack_handler.py",
            "webhook.py",
            "registry.py",
            "support.py",
        }
        allow_mods_prefix = ("lib.application.harness",)
        offenders: list[str] = []
        for path in ad_dir.rglob("*.py"):
            if path.name in allow:
                continue
            for mod in _imports_of(path):
                if not mod.startswith("lib.application"):
                    continue
                if any(mod == pref or mod.startswith(pref + ".") for pref in allow_mods_prefix):
                    continue
                offenders.append(f"{path.relative_to(ROOT)}:{mod}")
        self.assertEqual(offenders, [], msg=f"layer violation: {offenders}")


if __name__ == "__main__":
    unittest.main()
