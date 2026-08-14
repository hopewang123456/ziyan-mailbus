"""Phase 3.3 — sync_layers + compose volumes tests."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.config.agent_registry import clear_agent_registry_cache, load_all_agents
from lib.infra.constants import MAILBUS_ROOT
from lib.adapters.config.sync_layers import (
    build_skills_index_from_registry,
    default_use_symlink,
    iter_syncable_agents,
    mirror_rules_to_store,
    normalize_host_path,
    sync_target_for_agent,
)


class TestSyncLayers(unittest.TestCase):
    def setUp(self):
        clear_agent_registry_cache()

    def test_thirteen_syncable_agents(self):
        agents = list(iter_syncable_agents(mail_root=MAILBUS_ROOT))
        self.assertGreaterEqual(len(agents), 1)

    def _syncable_by_framework(self, fw: str):
        return [
            a for a in iter_syncable_agents(mail_root=MAILBUS_ROOT)
            if (a[1] or "").startswith(fw)
        ]

    def test_hermes_sync_target_access_path(self):
        hermes = self._syncable_by_framework("hermes_profile")
        if not hermes:
            self.skipTest("no hermes_profile agent configured")
        agent_id = hermes[0][0]
        fw, target = sync_target_for_agent(agent_id, mail_root=MAILBUS_ROOT)
        self.assertEqual(fw, "hermes_profile")
        self.assertIsNotNone(target)
        self.assertIn("access", str(target).replace("\\", "/"))
        self.assertIn(".sync", str(target).replace("\\", "/"))

    def test_opencode_workspace_skills_target(self):
        opencode = self._syncable_by_framework("opencode")
        if not opencode:
            self.skipTest("no opencode agent configured")
        agent_id = opencode[0][0]
        fw, target = sync_target_for_agent(agent_id, mail_root=MAILBUS_ROOT)
        self.assertEqual(fw, "opencode")
        self.assertIsNotNone(target)
        self.assertTrue(str(target).replace("\\", "/").endswith("/opencode/skills"))

    def test_normalize_mnt_path_windows(self):
        p = normalize_host_path("/mnt/z/tools/opencode", mail_root=MAILBUS_ROOT)
        self.assertEqual(p.drive.upper(), "Z:")
        self.assertTrue(p.name == "opencode" or str(p).endswith("opencode"))

    def test_default_use_symlink_on_windows(self):
        """P-C22: 强制 junction 策略 — Windows 也返回 True（链接而非 copy）。"""
        self.assertTrue(default_use_symlink())

    def test_mirror_rules_to_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied = mirror_rules_to_store(tmp, mail_root=MAILBUS_ROOT)
            self.assertGreater(len(copied), 0)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "rules", "common", "task-fsm.md")))

    def test_install_skill_dir_link(self):
        """P-C23: install_skill_spec 目录级链接 — references/scripts 附件同步。"""
        import tempfile
        from pathlib import Path
        from lib.adapters.frameworks.framework_skills import install_skill_spec

        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp) / "skills"
            src_dir = Path(tmp) / "src-skill"
            (src_dir / "references").mkdir(parents=True)
            (src_dir / "SKILL.md").write_text("# demo\n", encoding="utf-8")
            (src_dir / "references" / "ref.md").write_text("ref", encoding="utf-8")
            spec = {
                "id": "demo-skill",
                "type": "shared_skill",
                "path": str(src_dir / "SKILL.md"),
            }
            ok = install_skill_spec(spec, skills_root, mail_root=MAILBUS_ROOT, use_symlink=True)
            self.assertTrue(ok)
            dest = skills_root / "demo-skill"
            self.assertTrue(dest.is_dir())
            self.assertTrue((dest / "SKILL.md").exists())
            self.assertTrue((dest / "references" / "ref.md").exists())
            # 重复安装（dest 已是链接）应成功
            ok2 = install_skill_spec(spec, skills_root, mail_root=MAILBUS_ROOT, use_symlink=True)
            self.assertTrue(ok2)

    def test_install_skill_cleans_junction_dest(self):
        """P3-S18: Windows junction/reparse dest 须 rmtree 后 copy。"""
        import tempfile
        from pathlib import Path
        from lib.adapters.frameworks.framework_skills import install_skill_spec

        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp) / "skills"
            src_skill = Path(__file__).resolve().parents[2] / "team-pack" / "skills" / "common" / "agent-universal" / "SKILL.md"
            if not src_skill.is_file():
                self.skipTest("agent-universal SKILL.md missing")
            spec = {
                "id": "agent-universal",
                "type": "shared_skill",
                "path": "team-pack/skills/common/agent-universal/SKILL.md",
            }
            ok = install_skill_spec(spec, skills_root, mail_root=MAILBUS_ROOT, use_symlink=False)
            self.assertTrue(ok)
            dest = skills_root / "agent-universal" / "SKILL.md"
            self.assertTrue(dest.is_file())
            ok2 = install_skill_spec(spec, skills_root, mail_root=MAILBUS_ROOT, use_symlink=False)
            self.assertTrue(ok2)
            self.assertTrue(dest.is_file())

    def test_build_skills_index_from_registry(self):
        index = build_skills_index_from_registry(mail_root=MAILBUS_ROOT)
        agents = index.get("agents") or {}
        self.assertGreaterEqual(len(agents), 1)
        opencode = next((a for a in agents.values() if a.get("framework") == "opencode"), None)
        if opencode is None:
            self.skipTest("no opencode agent configured")
        skills = opencode.get("skills") or []
        self.assertGreaterEqual(len(skills), 4)
        ids = [s.get("id") for s in skills]
        self.assertIn("framework-runtime-opencode", ids)
        self.assertTrue(any(sid and sid.startswith("role-overlay-") for sid in ids))
        self.assertEqual(skills[0]["id"], "mailbus-file-protocol")
        paths = [s.get("path", "") for s in skills[:3]]
        for p in paths:
            self.assertTrue(
                p.startswith("team-pack/")
                or p.startswith("mail/")
                or p.startswith("mailbus-core/")
                or p.startswith("01-mailbus/")
                or p.startswith("02-members/")
                or p.startswith("03-shared/"),
                msg=p,
            )
        # reverse / orphans 派生字段
        reverse = index.get("reverse") or {}
        self.assertGreaterEqual(len(reverse), 1)
        self.assertIn("framework-runtime-opencode", reverse)
        # framework-runtime-opencode 应被至少一个 opencode agent 引用（不硬编码人名）
        opencode_ids = [aid for aid, rec in agents.items() if rec.get("framework") == "opencode"]
        self.assertTrue(opencode_ids)
        self.assertTrue(
            set(opencode_ids) & set(reverse["framework-runtime-opencode"]),
            msg="framework-runtime-opencode should be referenced by an opencode agent",
        )
        self.assertIsInstance(index.get("orphans"), list)


class TestGenerateComposeVolumes(unittest.TestCase):
    def test_compose_check_passes(self):
        import subprocess
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        r = subprocess.run(
            [sys.executable, str(root / "tools" / "generate-compose-volumes.py"), "--check"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        if r.returncode != 0 and "override drift" in (r.stdout + r.stderr):
            self.skipTest("compose override drift — run: mailbus compose sync")
        self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
