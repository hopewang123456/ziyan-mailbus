"""Phase 3 — agent_registry tests."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.agent_registry import (
    load_all_agents,
    get_agent,
    list_agent_ids,
    layer_skills_for_agent,
    resolve_skill_src,
    hermes_profile_agents,
    clear_agent_registry_cache,
    agent_archetypes,
)
from lib.constants import MAILBUS_ROOT


class TestAgentRegistry(unittest.TestCase):
    def setUp(self):
        clear_agent_registry_cache()

    def test_load_thirteen_agents(self):
        agents = load_all_agents(refresh=True)
        self.assertEqual(len(agents), 13)
        self.assertIn("dali", agents)
        self.assertIn("lingzhao", agents)

    def test_agent_record_fields(self):
        rec = get_agent("dali")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["framework"], "opencode")
        self.assertEqual(rec["archetype"], "coding-executor")
        self.assertEqual(rec["schema"], "mailbus-transport-v1")
        self.assertTrue(rec.get("skills"))

    def test_hermes_profile_roster(self):
        hp = hermes_profile_agents()
        self.assertIn("lingzhao", hp)
        self.assertIn("lingzhang", hp)
        self.assertNotIn("dali", hp)

    def test_archetypes_cover_all_agents(self):
        arch = agent_archetypes()
        for aid in list_agent_ids():
            self.assertIn(aid, arch, msg=f"missing archetype for {aid}")

    def test_layer_skills_for_dali(self):
        specs = layer_skills_for_agent("dali", "opencode")
        self.assertEqual(len(specs), 5)
        ids = [s["id"] for s in specs]
        self.assertIn("agent-universal", ids)
        self.assertIn("framework-runtime-opencode", ids)
        self.assertIn("role-overlay-dali", ids)

    def test_resolve_skill_src_v3_path(self):
        src = resolve_skill_src("team-pack/skills/common/agent-universal")
        from lib.constants import TEAM_PACK_ROOT
        expected = TEAM_PACK_ROOT / "skills" / "common" / "agent-universal" / "SKILL.md"
        self.assertEqual(src.resolve(), expected.resolve())
        self.assertTrue(src.is_file(), msg=str(src))


if __name__ == "__main__":
    unittest.main()
