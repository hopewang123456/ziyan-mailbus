"""cmd_agent_add 升格回归（W3 agents register 一等命令）。

覆盖：通用卡补齐、外部框架（store/frameworks/*.json）放行、模型默认、
agent_types fallback、workspace/home 目录创建、config 备份、重复/未知拒绝。
"""
import json
import os
import sys
import glob
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.infra.framework_spec import FRAMEWORKS


def _args(agent, **kw):
    base = dict(
        agent=agent, type="none", role="", display_name=None, archetype=None,
        models=None, agent_id=None, profile=None, push_cwd=None, home_dir=None,
        cli="", data_dir=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class _RegisterTestBase(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp(prefix="mb-reg-")
        self.config_path = os.path.join(self.data_dir, "config.json")
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"data_dir": self.data_dir, "agents": {}, "agent_types": {}}, f)
        os.makedirs(os.path.join(self.data_dir, "inbox"), exist_ok=True)

    def tearDown(self):
        from lib.adapters.frameworks.registry import unregister_framework
        unregister_framework("testbuddy")
        FRAMEWORKS.pop("testbuddy", None)

    def _run(self, agent, **kw):
        from lib.application.commands.commands import cmd_agent_add
        kw.setdefault("data_dir", self.data_dir)
        return cmd_agent_add(_args(agent, **kw))

    def _config(self) -> dict:
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_external(self):
        fw_dir = os.path.join(self.data_dir, "frameworks")
        os.makedirs(fw_dir, exist_ok=True)
        with open(os.path.join(fw_dir, "testbuddy.json"), "w", encoding="utf-8") as f:
            json.dump({
                "type_name": "testbuddy", "label": "TestBuddy CLI",
                "push_template": "testbuddy -p 'MSG'",
                "default_models": ["fake-model"],
                "file_task": True,
            }, f, ensure_ascii=False)


class TestAgentRegister(_RegisterTestBase):
    def test_basic_card_fields(self):
        rc = self._run("ling1", type="hermes_profile", display_name="灵一", role="通用工程")
        self.assertEqual(rc, 0)
        card = self._config()["agents"]["ling1"]
        self.assertEqual(card["name"], "灵一")
        self.assertEqual(card["type"], "hermes_profile")
        self.assertEqual(card["agent_id"], "ling1")
        self.assertEqual(card["max_concurrency"], 1)
        self.assertTrue(card["available"] and card["enabled"])
        self.assertEqual(card["profile"], "ling1")
        self.assertTrue(os.path.isfile(card["inbox"]))

    def test_builtin_models_default_from_spec(self):
        rc = self._run("ling2", type="zcode")
        self.assertEqual(rc, 0)
        self.assertEqual(self._config()["agents"]["ling2"]["models"], ["glm"])

    def test_unknown_type_rejected(self):
        rc = self._run("ling3", type="no_such_fw")
        self.assertEqual(rc, 1)
        self.assertNotIn("ling3", self._config()["agents"])

    def test_duplicate_rejected(self):
        self.assertEqual(self._run("ling4", type="none"), 0)
        self.assertEqual(self._run("ling4", type="none"), 1)

    def test_dirs_and_backup_created(self):
        cwd_dir = os.path.join(self.data_dir, "ws", "ling5")
        home_dir = os.path.join(self.data_dir, "homes", ".tb-ling5")
        rc = self._run("ling5", type="none", push_cwd=cwd_dir, home_dir=home_dir)
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isdir(cwd_dir))
        self.assertTrue(os.path.isdir(home_dir))
        self.assertEqual(self._config()["agents"]["ling5"]["push"]["cwd"], cwd_dir)
        backups = glob.glob(self.config_path + ".bak-agent-add-*")
        self.assertTrue(backups, "config 备份应存在")

    def test_agent_types_fallback_for_builtin(self):
        # store agent_types 缺条目的内置框架 → 注册时补（文档性 fallback）
        rc = self._run("ling6", type="cursor")
        self.assertEqual(rc, 0)
        self.assertIn("cursor", self._config()["agent_types"])


class TestAgentRegisterExternal(_RegisterTestBase):
    def test_external_framework_accepted_with_defaults(self):
        self._write_external()
        rc = self._run("lingcb", type="testbuddy")
        self.assertEqual(rc, 0)
        cfg = self._config()
        card = cfg["agents"]["lingcb"]
        self.assertEqual(card["type"], "testbuddy")
        self.assertEqual(card["models"], ["fake-model"])
        self.assertEqual(card["run_target"], "windows")
        self.assertEqual(cfg["agent_types"]["testbuddy"]["push"], "testbuddy -p 'MSG'")
        self.assertEqual(cfg["agent_types"]["testbuddy"]["description"], "TestBuddy CLI")


if __name__ == "__main__":
    unittest.main()
