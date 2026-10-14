"""外部框架 descriptor 加载（W2 配置化接入通道）回归。

store/frameworks/*.json = 零代码接入：加载注册、幂等、毒文件隔离、
config 校验放行、模板命令构建、file_task 动态生效、ensure 入口接线。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.frameworks.spec import FRAMEWORKS

CODEBUDDY_LIKE = {
    "type_name": "testbuddy",
    "label": "TestBuddy CLI",
    "note": "W2 通道回归用假框架",
    "cli_bin": "testbuddy",
    "default_models": ["fake-model"],
    "file_task": True,
    "mark_processing_on_task_push": True,
    "push_template": "testbuddy -p 'MSG' --model MODEL",
}


class _ExternalTestBase(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp(prefix="mb-extfw-")
        fw_dir = os.path.join(self.data_dir, "frameworks")
        os.makedirs(fw_dir, exist_ok=True)
        self.fw_dir = fw_dir

    def tearDown(self):
        # 全局表清理：测试注入的框架必须摘除，防污染其他用例
        from lib.adapters.frameworks.registry import unregister_framework
        unregister_framework("testbuddy")
        unregister_framework("poisonbuddy")
        FRAMEWORKS.pop("testbuddy", None)
        FRAMEWORKS.pop("poisonbuddy", None)

    def _write(self, fname: str, payload) -> str:
        path = os.path.join(self.fw_dir, fname)
        with open(path, "w", encoding="utf-8") as fh:
            if isinstance(payload, str):
                fh.write(payload)
            else:
                json.dump(payload, fh, ensure_ascii=False)
        return path


class TestLoadExternalFrameworks(_ExternalTestBase):
    def test_load_registers_spec_and_adapter(self):
        from lib.adapters.frameworks.external import load_external_frameworks
        self._write("testbuddy.json", CODEBUDDY_LIKE)
        rows = load_external_frameworks(self.data_dir)
        self.assertTrue(rows[0]["ok"], rows)
        self.assertIn("testbuddy", FRAMEWORKS)
        spec = FRAMEWORKS["testbuddy"]
        self.assertEqual(spec.label, "TestBuddy CLI")
        self.assertTrue(spec.file_task)
        self.assertEqual(spec.run_targets, ("windows",))
        from lib.adapters.frameworks.registry import get_adapter
        adapter = get_adapter("testbuddy")
        self.assertIsNotNone(adapter)
        self.assertTrue(adapter.mark_processing_on_task_push)

    def test_load_idempotent(self):
        from lib.adapters.frameworks.external import load_external_frameworks
        self._write("testbuddy.json", CODEBUDDY_LIKE)
        load_external_frameworks(self.data_dir)
        rows = load_external_frameworks(self.data_dir)
        self.assertTrue(rows[0]["skipped"], rows)

    def test_poison_file_isolated(self):
        from lib.adapters.frameworks.external import load_external_frameworks
        self._write("testbuddy.json", CODEBUDDY_LIKE)
        self._write("poison.json", "{ not valid json !!!")
        bad_spec = dict(CODEBUDDY_LIKE)
        bad_spec["type_name"] = "poisonbuddy"
        bad_spec["mystery_field"] = 1
        self._write("poison2.json", bad_spec)
        rows = {r["file"]: r for r in load_external_frameworks(self.data_dir)}
        self.assertTrue(rows["testbuddy.json"]["ok"])
        self.assertFalse(rows["poison.json"]["ok"])
        self.assertFalse(rows["poison2.json"]["ok"])
        self.assertIn("未知字段", rows["poison2.json"]["error"])
        self.assertNotIn("poisonbuddy", FRAMEWORKS)

    def test_missing_required_field_rejected(self):
        from lib.adapters.frameworks.external import load_external_frameworks
        incomplete = {"type_name": "testbuddy", "label": "x"}  # 缺 push_template
        self._write("testbuddy.json", incomplete)
        rows = load_external_frameworks(self.data_dir)
        self.assertFalse(rows[0]["ok"])
        self.assertIn("push_template", rows[0]["error"])

    def test_ensure_entry_point_loads_json(self):
        """ensure_framework_plugins_loaded 挂载 JSON 扫描（serve/scan 共用入口）。"""
        from lib.adapters.frameworks.entry_point_discovery import (
            ensure_framework_plugins_loaded,
        )
        self._write("testbuddy.json", CODEBUDDY_LIKE)
        ensure_framework_plugins_loaded(data_dir=self.data_dir)
        self.assertIn("testbuddy", FRAMEWORKS)

    def test_push_argv_registers_direct_builder(self):
        """push_argv 声明 → direct builder 注册（argv 直启，{MSG} 槽替换）。"""
        from lib.adapters.frameworks.external import load_external_frameworks
        from lib.adapters.frameworks.direct_push import (
            DIRECT_BUILDERS, try_build_push_direct,
        )
        from lib.adapters.frameworks.registry import (
            NoneAdapter, register_framework, unregister_framework,
        )
        spec = dict(CODEBUDDY_LIKE)
        # argv[0] 须在 spawn_guard 白名单（try_build 末尾校验）
        spec["push_argv"] = ["python", "-p", "{MSG}", "-y"]
        self._write("testbuddy.json", spec)
        load_external_frameworks(self.data_dir)
        self.assertIn("testbuddy", DIRECT_BUILDERS)
        long_msg = "含 '单引号' 与 \"双引号\" 和\n换行的长消息 —— shell 转义必炸的形态"
        out = try_build_push_direct(
            "ling-test", {"type": "testbuddy"}, {},
            data_dir="", prompt=long_msg, model_name=None,
        )
        # argv 直启：消息作为独立元素完整保留，不经 shell 转义
        self.assertEqual(out["argv"], ["python", "-p", long_msg, "-y"])
        unregister_framework("testbuddy")
        DIRECT_BUILDERS.pop("testbuddy", None)
        register_framework("testbuddy", NoneAdapter())  # tearDown 只清 FRAMEWORKS/ADAPTERS

    def test_push_argv_without_msg_slot(self):
        """无 {MSG} 槽的 push_argv（纯通知型）也合法。"""
        from lib.adapters.frameworks.external import load_external_frameworks
        from lib.adapters.frameworks.direct_push import try_build_push_direct
        spec = dict(CODEBUDDY_LIKE)
        spec["push_argv"] = ["python", "--version"]
        self._write("testbuddy.json", spec)
        load_external_frameworks(self.data_dir)
        out = try_build_push_direct(
            "ling-test", {"type": "testbuddy"}, {},
            data_dir="", prompt="", model_name=None,
        )
        self.assertEqual(out["argv"], ["python", "--version"])


class TestExternalFrameworkEffects(_ExternalTestBase):
    def setUp(self):
        super().setUp()
        from lib.adapters.frameworks.external import load_external_frameworks
        self._write("testbuddy.json", CODEBUDDY_LIKE)
        load_external_frameworks(self.data_dir)

    def _bare_config(self, agent_type: str) -> dict:
        return {
            "project": "p", "version": "1.0.0", "data_dir": self.data_dir,
            "ack_timeout": 30, "max_retries": 3, "archive_days": 3,
            "archive_max_messages": 300,
            "agents": {"b": {"type": agent_type}},
        }

    def test_validate_config_accepts_external_type(self):
        from lib.adapters.config.config_schema import validate_config
        errors = validate_config(self._bare_config("testbuddy"))
        self.assertFalse([e for e in errors if "不支持的 agent 类型" in e], errors)

    def test_validate_config_still_rejects_unknown_type(self):
        from lib.adapters.config.config_schema import validate_config
        errors = validate_config(self._bare_config("no_such_fw"))
        self.assertTrue(any("不支持的 agent 类型" in e for e in errors), errors)

    def test_external_type_not_in_static_enum(self):
        """外部框架不进静态 AGENT_TYPES（import 时固化的内置集）。"""
        from lib.adapters.config.config_schema import AGENT_TYPES
        self.assertNotIn("testbuddy", AGENT_TYPES)

    def test_template_adapter_builds_command(self):
        from lib.adapters.frameworks.registry import get_adapter
        adapter = get_adapter("testbuddy")
        agent_cfg = {"agent": "ling-test", "models": ["fake-model"]}
        agent_types = {"models": {"fake-model": {"testbuddy": "--model fake-model"}}}
        cmd = adapter.build_push_cli("ling-test", agent_cfg, agent_types, "fake-model")
        self.assertEqual(cmd, "testbuddy -p 'MSG' --model fake-model")
        # 无 model 配置时 --model MODEL 残段清空
        cmd2 = adapter.build_push_cli("ling-test", {"agent": "ling-test"}, {}, None)
        self.assertEqual(cmd2, "testbuddy -p 'MSG' ")

    def test_file_task_dynamic(self):
        from lib.application.orchestration.file_task_push import (
            agent_uses_file_task_push,
        )
        self.assertTrue(agent_uses_file_task_push("testbuddy"))
        self.assertFalse(agent_uses_file_task_push("hermes_profile"))

    def test_cli_active_matches_declared_bin(self):
        from lib.adapters.frameworks.registry import get_adapter
        adapter = get_adapter("testbuddy")
        self.assertTrue(adapter.cli_active_in_ps("a", {}, "node.exe testbuddy -p x"))
        self.assertFalse(adapter.cli_active_in_ps("a", {}, "python.exe other.py"))


if __name__ == "__main__":
    unittest.main()
