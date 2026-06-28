"""Phase 3.3 — sync_layers + compose volumes tests."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.agent_registry import clear_agent_registry_cache, load_all_agents
from lib.constants import MAILBUS_ROOT
from lib.sync_layers import (
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
        self.assertEqual(len(agents), 13)

    def test_hermes_sync_target_v3_path(self):
        fw, target = sync_target_for_agent("lingzhao", mail_root=MAILBUS_ROOT)
        self.assertEqual(fw, "hermes_profile")
        self.assertIsNotNone(target)
        self.assertIn("access", str(target).replace("\\", "/"))
        self.assertIn(".sync", str(target).replace("\\", "/"))

    def test_dali_workspace_skills_target(self):
        fw, target = sync_target_for_agent("dali", mail_root=MAILBUS_ROOT)
        self.assertEqual(fw, "opencode")
        self.assertIsNotNone(target)
        self.assertTrue(str(target).replace("\\", "/").endswith("/opencode/skills"))

    def test_normalize_mnt_path_windows(self):
        p = normalize_host_path("/mnt/e/ai_tools/opencode", mail_root=MAILBUS_ROOT)
        self.assertEqual(p.drive.upper(), "E:")
        self.assertTrue(p.name == "opencode" or str(p).endswith("opencode"))

    def test_default_use_symlink_on_windows(self):
        if sys.platform == "win32":
            self.assertFalse(default_use_symlink())
        else:
            self.assertTrue(default_use_symlink())

    def test_mirror_rules_to_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied = mirror_rules_to_store(tmp, mail_root=MAILBUS_ROOT)
            self.assertGreater(len(copied), 0)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "rules", "common", "task-fsm.md")))

    def test_install_skill_cleans_junction_dest(self):
        """P3-S18: Windows junction/reparse dest 须 rmtree 后 copy。"""
        import tempfile
        from pathlib import Path
        from lib.framework_skills import install_skill_spec

        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp) / "skills"
            src_skill = MAILBUS_ROOT / "skills" / "common" / "agent-universal" / "SKILL.md"
            if not src_skill.is_file():
                self.skipTest("agent-universal SKILL.md missing")
            spec = {
                "id": "agent-universal",
                "type": "shared_skill",
                "path": "mail/skills/common/agent-universal/SKILL.md",
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
        self.assertEqual(len(agents), 13)
        dali = agents["dali"]
        self.assertEqual(dali["framework"], "opencode")
        skills = dali.get("skills") or []
        self.assertGreaterEqual(len(skills), 5)
        self.assertEqual(skills[0]["id"], "agent-universal")
        paths = [s.get("path", "") for s in skills[:3]]
        for p in paths:
            self.assertIn("mail/skills/", p)


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
        self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
