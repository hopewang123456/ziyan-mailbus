"""Phase 3 — rules_registry tests."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.config.rules_registry import (
    rule_paths_for_agent,
    resolved_rule_paths,
    default_rule_paths,
    rules_by_layer,
    resolve_rule_path,
)
from lib.infra.constants import AGENT_VAULT_ROOT, MAILBUS_ROOT


class TestRulesRegistry(unittest.TestCase):
    def _opencode_agent(self):
        from lib.adapters.config.agent_registry import list_agents_by_framework
        oc = list_agents_by_framework("opencode")
        return oc[0] if oc else None

    def test_opencode_explicit_rules(self):
        aid = self._opencode_agent()
        if not aid:
            self.skipTest("no opencode agent configured")
        rels = rule_paths_for_agent(aid)
        self.assertTrue(any("0111-common/execution-order" in r for r in rels))
        self.assertTrue(any("0111-common/task-fsm" in r for r in rels))
        self.assertTrue(any("0141-positions/coding-executor/boundaries" in r for r in rels))

    def test_default_derivation(self):
        rels = default_rule_paths("spec-designer", "hermes_profile")
        self.assertIn("01-mailbus/011-rule/0112-frameworks/hermes_profile/delivery", rels)
        self.assertIn("01-mailbus/014-team/0141-positions/spec-designer/boundaries", rels)

    def test_resolved_paths_exist(self):
        from lib.adapters.config.agent_registry import load_all_agents
        agents = load_all_agents()
        self.assertGreaterEqual(len(agents), 1)
        aid = next(iter(agents))
        paths = resolved_rule_paths(aid, existing_only=True)
        self.assertGreaterEqual(len(paths), 3)
        for p in paths:
            self.assertTrue(p.is_file(), msg=str(p))

    def test_rules_by_layer(self):
        from lib.adapters.config.agent_registry import list_agents_by_framework, load_all_agents
        agents = load_all_agents()
        self.assertGreaterEqual(len(agents), 1)
        # 用 hermes agent 验证（框架 delivery 规则存在）
        hermes = list_agents_by_framework("hermes_profile")
        aid = hermes[0] if hermes else next(iter(agents))
        grouped = rules_by_layer(aid)
        self.assertTrue(grouped["common"])
        self.assertTrue(grouped["frameworks"])
        self.assertTrue(grouped["roles"])

    def test_resolve_rule_path_vault(self):
        p = resolve_rule_path("01-mailbus/011-rule/0111-common/task-fsm")
        self.assertEqual(
            p.resolve(),
            (AGENT_VAULT_ROOT / "01-mailbus" / "011-rule" / "0111-common" / "task-fsm.md").resolve(),
        )
        self.assertTrue(p.is_file(), msg=str(p))

    def test_resolve_rule_path_repo_fallback(self):
        p = resolve_rule_path("mailbus-core/rules/common/task-fsm.md")
        self.assertEqual(
            p.resolve(),
            (MAILBUS_ROOT / "rules" / "common" / "task-fsm.md").resolve(),
        )


if __name__ == "__main__":
    unittest.main()
