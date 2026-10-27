"""P1 二期 — 内置身份注册表（D2/D15）：SoT 合并 / agents 视图注入 / 改名。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from lib.infra.builtin_identities import (
    load_builtin_identities,
    merge_into_agents,
    rename_identity,
)


class TestBuiltinIdentities(unittest.TestCase):
    def test_seed_loads_ziyan_owner(self):
        idents = load_builtin_identities("")
        self.assertTrue(any(i["id"] == "ziyan" and i["role"] == "owner" for i in idents))

    def test_merge_into_agents_runtime_view(self):
        agents = merge_into_agents({"lingzhao": {"name": "灵昭"}}, "")
        self.assertIn("ziyan", agents)
        self.assertEqual(agents["ziyan"]["type"], "builtin")
        self.assertTrue(agents["ziyan"]["available"])
        self.assertNotIn("builtin", agents["lingzhao"])  # 普通agent不被误标

    def test_rename_persists_override_without_touching_seed(self):
        with tempfile.TemporaryDirectory() as td:
            updated = rename_identity(td, "ziyan", "老板")
            self.assertEqual(updated["display_name"], "老板")
            self.assertEqual(updated["role"], "owner")  # id/role 稳定
            # 覆盖文件已写，seed 未动
            ov = json.load(open(os.path.join(td, "config", "builtin-identities.json"), encoding="utf-8"))
            self.assertEqual(ov["identities"][0]["display_name"], "老板")
            # 重新加载走覆盖
            idents = load_builtin_identities(td)
            self.assertEqual(idents[0]["display_name"], "老板")
            # 未知身份 / 空名 → None
            self.assertIsNone(rename_identity(td, "ghost", "x"))
            self.assertIsNone(rename_identity(td, "ziyan", "  "))

    def test_rename_unknown_identity_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(rename_identity(td, "not-in-seed", "名"))


if __name__ == "__main__":
    unittest.main()
