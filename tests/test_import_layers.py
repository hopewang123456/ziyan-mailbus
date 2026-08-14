"""Guard layering after Wave 1 package renames."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "lib"

FORBIDDEN_TOP = {
    "ports",
    "transport",
    "workflow",
    "intake",
    "drill",
    "harness",
    "verify",
    "container",
    "locale",
    "scan",
    "push",
    "internal_llm",
}


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


class TestImportLayers(unittest.TestCase):
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
        from lib.interfaces.message_transport import MessageTransportPort

        self.assertTrue(AgentRef and Fatal and Retryable and BudgetPaused)
        self.assertTrue(AgentRuntimePort and ResultStorePort and TaskFsmPort)
        self.assertTrue(BudgetMeterPort and HumanGatePort and AuditPort)
        self.assertTrue(MessageTransportPort)

    def test_core_a2a_importable(self):
        import lib.core.a2a as a2a

        self.assertTrue(hasattr(a2a, "__file__") or hasattr(a2a, "__path__"))

    def test_old_free_packages_gone(self):
        for name in FORBIDDEN_TOP:
            self.assertFalse((ROOT / name).exists(), msg=f"old package still present: lib/{name}")

    def test_application_does_not_import_framework_adapters(self):
        app_dir = ROOT / "application"
        bad_prefix = "lib.adapters.frameworks"
        offenders: list[str] = []
        for path in app_dir.rglob("*.py"):
            for mod in _imports_of(path):
                if mod.startswith(bad_prefix):
                    offenders.append(f"{path.relative_to(ROOT)}:{mod}")
        self.assertEqual(offenders, [], msg=f"layer violation: {offenders}")

    def test_application_does_not_import_task_fsm(self):
        app_dir = ROOT / "application"
        bad = "lib.adapters.orchestration.task_fsm"
        offenders: list[str] = []
        for path in app_dir.rglob("*.py"):
            for mod in _imports_of(path):
                if mod == bad or mod.startswith(bad + "."):
                    offenders.append(f"{path.relative_to(ROOT)}:{mod}")
        self.assertEqual(offenders, [], msg=f"layer violation: {offenders}")

    def test_application_does_not_import_adapters(self):
        """Wave-3: application must not import lib.adapters (use composition/ports)."""
        app_dir = ROOT / "application"
        bad_prefix = "lib.adapters"
        offenders: list[str] = []
        for path in app_dir.rglob("*.py"):
            for mod in _imports_of(path):
                if mod == bad_prefix or mod.startswith(bad_prefix + "."):
                    offenders.append(f"{path.relative_to(ROOT)}:{mod}")
        self.assertEqual(offenders, [], msg=f"layer violation: {offenders}")

    def test_adapters_do_not_import_application(self):
        ad_dir = ROOT / "adapters"
        if not ad_dir.is_dir():
            self.skipTest("no adapters yet")
        allow = {
            "task_fsm.py",
            # Wave-2 relocated former lib-root modules (temporary debt)
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
        # Wave-1: harness now under application; file_bus/results still call it
        allow_mods_prefix = ("lib.application.harness",)
        offenders: list[str] = []
        for path in ad_dir.rglob("*.py"):
            if path.name in allow:
                continue
            for mod in _imports_of(path):
                if not mod.startswith("lib.application"):
                    continue
                if any(mod == p or mod.startswith(p + ".") for p in allow_mods_prefix):
                    continue
                offenders.append(f"{path.relative_to(ROOT)}:{mod}")
        self.assertEqual(offenders, [], msg=f"layer violation: {offenders}")


if __name__ == "__main__":
    unittest.main()
