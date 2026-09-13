"""Decoupling: no hard-coded ai_tools/Agent discovery paths."""
from __future__ import annotations

import inspect
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.adapters.config.browser_auth import openclaw_gateway_token
from lib.adapters.discovery import DirDiscoverySource
from lib.adapters.ops.layout_guard import layout_report


class TestDirDiscoveryNoAiToolsGuess(unittest.TestCase):
    def test_source_has_no_hardcoded_ai_tools_agent(self):
        src = inspect.getsource(DirDiscoverySource.scan)
        self.assertNotIn("ai_tools/Agent", src)
        self.assertNotIn("ai_tools\\Agent", src)

    def test_extra_dirs_env_used(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "openclaw_space"
            fake.mkdir()
            with patch.dict(os.environ, {"MAILBUS_DISCOVERY_DIRS": str(fake)}, clear=False):
                hits = DirDiscoverySource().scan()
            paths = [h.home_path for h in hits]
            self.assertTrue(any(str(fake) in p for p in paths))


class TestOpenclawTokenNoSiblingDocker(unittest.TestCase):
    def test_source_no_parent_docker_guess(self):
        src = inspect.getsource(openclaw_gateway_token)
        # 函数体（去掉 docstring）不得再拼兄弟仓 docker 路径
        body = src.split('"""', 2)[-1] if src.count('"""') >= 2 else src
        self.assertNotIn('parent / "docker"', body)
        self.assertNotIn("/docker/openclaw_space", body)
        self.assertNotIn("\\docker\\openclaw_space", body)

    def test_workspace_env_reads_json(self):
        with tempfile.TemporaryDirectory() as td:
            oc_dir = Path(td) / ".openclaw"
            oc_dir.mkdir()
            oc_json = oc_dir / "openclaw.json"
            oc_json.write_text(
                '{"gateway":{"auth":{"mode":"token","token":"from-workspace"}}}',
                encoding="utf-8",
            )
            env = {
                "OPENCLAW_GATEWAY_TOKEN": "",
                "OPENCLAW_WORKSPACE": td,
                "OPENCLAW_CONFIG": "",
            }
            with patch.dict(os.environ, env, clear=False):
                # clear token if set in outer env
                os.environ.pop("OPENCLAW_GATEWAY_TOKEN", None)
                self.assertEqual(openclaw_gateway_token(), "from-workspace")


class TestLayoutReportMailbus(unittest.TestCase):
    def test_prefers_mailbus_name(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "mailbus").mkdir()
            rep = layout_report(base)
            self.assertTrue(str(rep.mail_path).endswith("mailbus") or "mailbus" in str(rep.mail_path))
            self.assertIn("mailbus", rep.message.lower())


class TestMailbusPathPrefix(unittest.TestCase):
    def test_framework_skill_emits_mailbus_prefix(self):
        from lib.adapters.frameworks.framework_skills import framework_skill_path_rel, shared_protocol_spec

        self.assertTrue(framework_skill_path_rel("hermes").startswith("mailbus/skills/"))
        self.assertTrue(shared_protocol_spec()["path"].startswith("mailbus/skills/"))

    def test_resolve_mailbus_and_mail_skills_alias(self):
        from lib.adapters.config.agent_registry import resolve_skill_src
        from lib.infra.constants import MAILBUS_ROOT

        root = Path(MAILBUS_ROOT)
        a = resolve_skill_src("mailbus/skills/common/mailbus-file-protocol", mail_root=root)
        b = resolve_skill_src("mail/skills/common/mailbus-file-protocol", mail_root=root)
        self.assertEqual(a, b)
        self.assertTrue(a.is_file() or (a.parent / "SKILL.md").is_file() or a.name == "SKILL.md")


if __name__ == "__main__":
    unittest.main()
