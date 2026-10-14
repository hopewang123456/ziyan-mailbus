"""Wave5: MdAgentsConfig + CompositeConfigRepo."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lib.adapters.config.composite_config import CompositeConfigRepo
from lib.adapters.config.md_config import MdAgentsConfig, parse_frontmatter


class TestMdFrontmatter(unittest.TestCase):
    def test_parse_frontmatter(self):
        fm, body = parse_frontmatter(
            "---\nid: demo\ntype: codex\nrole: dev\nenabled: true\n---\n# Hello\n"
        )
        self.assertEqual(fm.get("id"), "demo")
        self.assertEqual(fm.get("type"), "codex")
        self.assertIn("Hello", body)

    def test_md_agents_from_agents_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents = Path(tmp) / "agents"
            agents.mkdir()
            (agents / "alpha.md").write_text(
                "---\nid: alpha\ntype: openclaw\nrole: ops\nmount: host\nenabled: true\n---\nbody\n",
                encoding="utf-8",
            )
            md = MdAgentsConfig(tmp)
            refs = md.list_agents()
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0].agent_id, "alpha")
            self.assertEqual(refs[0].framework, "openclaw")
            self.assertEqual(refs[0].role_id, "ops")
            self.assertTrue(refs[0].enabled)


class TestCompositeConfigRepo(unittest.TestCase):
    def test_md_overrides_json_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            store.mkdir()
            ids = Path(tmp) / "ids"
            agents = ids / "agents"
            agents.mkdir(parents=True)
            (agents / "a1.md").write_text(
                "---\nid: a1\ntype: hermes\nrole: lead\nenabled: true\n---\n",
                encoding="utf-8",
            )
            repo = CompositeConfigRepo(str(store), identities_root=str(ids))
            repo.update(
                lambda cfg: cfg.update(
                    {
                        "agents": {
                            "a1": {"type": "codex", "role": "dev", "enabled": False},
                            "a2": {"type": "codex", "role": "dev", "enabled": True},
                        }
                    }
                )
            )
            a1 = repo.get_agent("a1")
            a2 = repo.get_agent("a2")
            self.assertIsNotNone(a1)
            assert a1 is not None
            self.assertEqual(a1.framework, "hermes")
            self.assertEqual(a1.role_id, "lead")
            self.assertTrue(a1.enabled)
            self.assertIsNotNone(a2)
            assert a2 is not None
            self.assertEqual(a2.framework, "codex")
            ids_listed = {r.agent_id for r in repo.list_agents()}
            self.assertEqual(ids_listed, {"a1", "a2"})


if __name__ == "__main__":
    unittest.main()
