"""Phase 3 — agent_registry tests."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.config.agent_registry import (
    load_all_agents,
    list_agent_ids,
    list_agents_by_framework,
    layer_skills_for_agent,
    resolve_skill_src,
    hermes_profile_agents,
    clear_agent_registry_cache,
    agent_archetypes,
)
from lib.infra.constants import AGENT_VAULT_ROOT, MAILBUS_ROOT


class TestAgentRegistry(unittest.TestCase):
    def setUp(self):
        clear_agent_registry_cache()

    def test_load_thirteen_agents(self):
        agents = load_all_agents(refresh=True)
        self.assertGreaterEqual(len(agents), 1)
        fws = {r.get("framework") for r in agents.values()}
        self.assertTrue(fws & {"hermes_profile", "opencode", "codex", "claude_code", "openclaw"})

    def test_agent_record_fields(self):
        agents = load_all_agents()
        self.assertGreaterEqual(len(agents), 1)
        rec = next(iter(agents.values()))
        self.assertIn(rec.get("framework"), ("hermes_profile", "opencode", "codex", "claude_code", "openclaw"))
        self.assertIn(rec.get("schema"), ("mailbus-transport-v1", None))
        self.assertTrue(rec.get("skills"))
        self.assertTrue(rec.get("rules"))

    def test_hermes_profile_roster(self):
        hp = hermes_profile_agents()
        self.assertGreaterEqual(len(hp), 1)
        opencode = list_agents_by_framework("opencode")
        for oc in opencode:
            self.assertNotIn(oc, hp)

    def test_archetypes_cover_all_agents(self):
        arch = agent_archetypes()
        for aid in list_agent_ids():
            self.assertIn(aid, arch, msg=f"missing archetype for {aid}")

    def test_layer_skills_for_opencode(self):
        opencode = list_agents_by_framework("opencode")
        if not opencode:
            self.skipTest("no opencode agent configured")
        aid = opencode[0]
        specs = layer_skills_for_agent(aid, "opencode")
        self.assertGreaterEqual(len(specs), 4)
        ids = [s["id"] for s in specs]
        self.assertIn("mailbus-file-protocol", ids)
        self.assertIn("framework-runtime-opencode", ids)
        self.assertTrue(any(sid.startswith("role-overlay-") for sid in ids))

    def test_resolve_skill_src_v3_path(self):
        src = resolve_skill_src("02-members/021-common/0211-rules/agent-universal")
        expected = AGENT_VAULT_ROOT / "02-members" / "021-common" / "0211-rules" / "agent-universal" / "SKILL.md"
        self.assertEqual(src.resolve(), expected.resolve())
        self.assertTrue(src.is_file(), msg=str(src))


if __name__ == "__main__":
    unittest.main()
