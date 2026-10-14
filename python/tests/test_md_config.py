"""Wave5: parse repo seed agent Markdown frontmatter."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.adapters.config.md_config import MdAgentsConfig, parse_frontmatter, resolve_identities_root
from lib.infra.constants import PROJECT_ROOT_STR

_FIXTURE_IDS = Path(__file__).resolve().parent / "fixtures" / "vault" / "identities"


class TestSeedAgentMd(unittest.TestCase):
    def test_repo_example_agent_md_parses(self):
        md_path = Path(PROJECT_ROOT_STR) / "config" / "agents" / "example-agent.md"
        self.assertTrue(md_path.is_file(), msg=str(md_path))
        text = md_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        self.assertEqual(fm.get("id"), "example-agent")
        self.assertEqual(fm.get("type"), "hermes")
        self.assertEqual(fm.get("role"), "demo")
        self.assertTrue(fm.get("enabled"))
        self.assertIn("Example Agent", body)

    def test_fixture_identities_root_finds_example_agent(self):
        """Use tests/fixtures/vault/identities so CI/local pass without Vault junction."""
        self.assertTrue(_FIXTURE_IDS.is_dir(), msg=str(_FIXTURE_IDS))
        root = resolve_identities_root(config={}, override=str(_FIXTURE_IDS))
        md = MdAgentsConfig(root)
        entry = md.get_agent_entry("example-agent")
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.get("type"), "hermes")
        self.assertEqual(entry.get("role_id"), "demo")
        ref = md.get_agent("example-agent")
        self.assertIsNotNone(ref)
        assert ref is not None
        self.assertEqual(ref.agent_id, "example-agent")
        self.assertTrue(ref.enabled)


if __name__ == "__main__":
    unittest.main()
