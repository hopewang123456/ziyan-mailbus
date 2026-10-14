"""实例/角色装配语义 — assemble 模块（skillgroup / skills 合并 / persona V1 / role_view 聚合）。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import lib.adapters.config.assemble as assemble


class TestSkillgroupScan(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._orig_root = assemble.MAILBUS_SKILLGROUP_ROOT
        assemble.MAILBUS_SKILLGROUP_ROOT = self.root
        # 组：writing / media；点目录 .hidden 与裸文件 readme.txt 应被忽略
        (self.root / "writing" / "style-guide").mkdir(parents=True)
        (self.root / "writing" / "style-guide" / "SKILL.md").write_text("# style", encoding="utf-8")
        (self.root / "writing" / "translation.md").write_text("# translation", encoding="utf-8")
        (self.root / "media" / "video-publish").mkdir(parents=True)
        (self.root / "media" / "video-publish" / "SKILL.md").write_text("# video", encoding="utf-8")
        (self.root / ".hidden").mkdir()
        (self.root / "readme.txt").write_text("not a group", encoding="utf-8")

    def tearDown(self):
        assemble.MAILBUS_SKILLGROUP_ROOT = self._orig_root
        self._tmp.cleanup()

    def test_list_skill_groups_returns_dirs_only(self):
        groups = assemble.list_skill_groups()
        self.assertEqual(groups, ["media", "writing"])

    def test_skills_in_group_scans_dirs_and_md(self):
        specs = assemble.skills_in_group("writing")
        ids = sorted(s["id"] for s in specs)
        self.assertEqual(ids, ["style-guide", "translation"])
        for s in specs:
            self.assertEqual(s["type"], "skillgroup")
            self.assertEqual(s["skillgroup"], "writing")

    def test_unknown_group_returns_empty(self):
        self.assertEqual(assemble.skills_in_group("nope"), [])


class TestMergeById(unittest.TestCase):
    def test_same_id_later_wins_keeps_first_order(self):
        framework = {"id": "writing", "path": "/fw/writing/SKILL.md", "type": "framework_skill"}
        group = {"id": "writing", "path": "/sg/writing/SKILL.md", "type": "skillgroup"}
        private = {"id": "writing", "path": "/role/writing/SKILL.md", "type": "role_overlay"}
        merged = assemble._merge_by_id([framework, group, private])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["type"], "role_overlay")  # 私有覆盖框架/组

    def test_distinct_ids_all_kept(self):
        merged = assemble._merge_by_id(
            [
                {"id": "a", "path": "/a"},
                {"id": "b", "path": "/b"},
                {"id": "c", "path": "/c"},
            ]
        )
        self.assertEqual([m["id"] for m in merged], ["a", "b", "c"])


class TestPersonaV1(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_verify_persona_files_flags_missing_only(self):
        existing = self.root / "SOUL.md"
        existing.write_text("soul", encoding="utf-8")
        missing = self.root / "nope.md"
        result = assemble.verify_persona_files([str(existing), str(missing)])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["path"], str(missing))
        self.assertFalse(result[0]["exists"])

    def test_verify_persona_files_all_present_returns_empty(self):
        existing = self.root / "SOUL.md"
        existing.write_text("soul", encoding="utf-8")
        self.assertEqual(assemble.verify_persona_files([str(existing)]), [])


class TestRoleView(unittest.TestCase):
    """方案 B：role_view 正确聚合角色运行时层（config.json agents）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.config = self.data_dir / "config.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _write_config(self, agents: dict):
        import json

        self.config.write_text(json.dumps({"agents": agents}, ensure_ascii=False), encoding="utf-8")

    def test_role_view_reads_role_layer_from_data_dir(self):
        self._write_config(
            {
                "foo": {
                    "type": "hermes_profile",
                    "paths": {"persona": "E:/persona/foo"},
                    "skill_groups": ["writing", ""],
                    "persona_files": ["E:/persona/foo/SOUL.md"],
                }
            }
        )
        view = assemble.role_view("foo", data_dir=self.data_dir)
        self.assertEqual(view["framework"], "hermes_profile")  # transport 空 → 回退 role.type
        self.assertEqual(view["paths"]["persona"], "E:/persona/foo")
        self.assertEqual(view["skill_groups"], ["writing"])  # 空字符串被过滤
        self.assertEqual(view["persona_files"], ["E:/persona/foo/SOUL.md"])

    def test_role_view_unknown_agent_returns_empty(self):
        self._write_config({})
        view = assemble.role_view("ghost", data_dir=self.data_dir)
        self.assertEqual(view["framework"], "")
        self.assertEqual(view["skill_groups"], [])
        self.assertEqual(view["persona_files"], [])


class TestPatchKeys(unittest.TestCase):
    def test_agent_patch_keys_include_new_fields(self):
        from lib.adapters.config.config_admin import AGENT_PATCH_KEYS

        self.assertIn("skill_groups", AGENT_PATCH_KEYS)
        self.assertIn("persona_files", AGENT_PATCH_KEYS)


if __name__ == "__main__":
    unittest.main()
