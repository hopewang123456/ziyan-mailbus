"""L3 轻量装配器测试（P0c，D7/D8）— 注册表 + 声明式配置查表组装。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from lib.composition.assembler import assemble, load_composition_config
from lib.interfaces.assembler import (
    REGISTRY,
    AssemblyError,
    register,
    registered_impls,
    resolve_factory,
)


class TestRegistry(unittest.TestCase):
    def test_register_and_resolve(self):
        @register("test_slot", "alpha")
        def _alpha(ctx):
            return ("alpha", ctx["data_dir"])

        @register("test_slot", "beta")
        def _beta(ctx):
            return ("beta", ctx["data_dir"])

        self.assertEqual(registered_impls("test_slot"), ("alpha", "beta"))
        self.assertEqual(resolve_factory("test_slot", "alpha")({"data_dir": "x"})[0], "alpha")

    def test_duplicate_registration_raises(self):
        @register("dup_slot", "one")
        def _one(ctx):
            return None

        with self.assertRaises(AssemblyError):
            @register("dup_slot", "one")
            def _one_again(ctx):
                return None

    def test_unknown_choice_fail_fast(self):
        with self.assertRaises(AssemblyError) as cm:
            resolve_factory("nonexistent_slot", "whatever")
        self.assertIn("未知", str(cm.exception))


class TestAssemble(unittest.TestCase):
    def test_default_when_config_missing(self):
        # 无 composition 段 → default 生效（既有行为零迁移）
        from lib.adapters.orchestration.audit import FileAuditAdapter, NoopAudit

        with tempfile.TemporaryDirectory() as td:
            got = assemble("audit", td, default="noop")
            self.assertIsInstance(got, NoopAudit)
            got = assemble("audit", td, default="file")
            self.assertIsInstance(got, FileAuditAdapter)

    def test_declared_choice_wins(self):
        from lib.adapters.orchestration.audit import FileAuditAdapter

        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "config.json"), "w", encoding="utf-8") as f:
                json.dump({"composition": {"audit": "file"}}, f)
            comp = load_composition_config(td)
            self.assertEqual(comp.get("audit"), "file")
            got = assemble("audit", td, default="noop", config=comp)
            self.assertIsInstance(got, FileAuditAdapter)

    def test_unknown_declared_impl_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "config.json"), "w", encoding="utf-8") as f:
                json.dump({"composition": {"audit": "sqlite-ghost"}}, f)
            with self.assertRaises(AssemblyError):
                assemble("audit", td, default="noop")

    def test_notifier_registered(self):
        from lib.adapters.orchestration.notifier import FileNotifier

        self.assertIn("file", registered_impls("notifier"))
        got = assemble("notifier", "store", default="file", config={})
        self.assertIsInstance(got, FileNotifier)


class TestBuildOrchestrationL3(unittest.TestCase):
    """factories.build_orchestration 经装配器选择 audit（env 兼容保留）。"""

    def test_default_file_audit(self):
        from lib.adapters.orchestration.audit import FileAuditAdapter
        from lib.composition.factories import build_orchestration

        with tempfile.TemporaryDirectory() as td:
            bundle = build_orchestration(td)
            self.assertIsInstance(bundle.audit, FileAuditAdapter)

    def test_env_off_falls_to_noop(self):
        from lib.adapters.orchestration.audit import NoopAudit
        from lib.composition.factories import build_orchestration

        os.environ["MAILBUS_FILE_AUDIT"] = "0"
        try:
            with tempfile.TemporaryDirectory() as td:
                bundle = build_orchestration(td)
                self.assertIsInstance(bundle.audit, NoopAudit)
        finally:
            del os.environ["MAILBUS_FILE_AUDIT"]

    def test_composition_section_overrides_default(self):
        from lib.adapters.orchestration.audit import NoopAudit
        from lib.composition.factories import build_orchestration

        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "config.json"), "w", encoding="utf-8") as f:
                json.dump({"composition": {"audit": "noop"}}, f)
            bundle = build_orchestration(td)  # default=file, 但声明 noop 胜出
            self.assertIsInstance(bundle.audit, NoopAudit)


if __name__ == "__main__":
    unittest.main()
