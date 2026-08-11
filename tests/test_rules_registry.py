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
from lib.infra.constants import MAILBUS_ROOT


class TestRulesRegistry(unittest.TestCase):
    def test_dali_explicit_rules(self):
        rels = rule_paths_for_agent("dali")
        self.assertTrue(any("execution-order.md" in r for r in rels))
        self.assertTrue(any("frameworks/opencode/delivery.md" in r for r in rels))
        self.assertTrue(any("roles/coding-executor/boundaries.md" for r in rels))

    def test_default_derivation(self):
        rels = default_rule_paths("spec-designer", "hermes_profile")
        self.assertIn("mailbus-core/rules/frameworks/hermes_profile/delivery.md", rels)
        self.assertIn("team-pack/rules/roles/spec-designer/boundaries.md", rels)

    def test_resolved_paths_exist(self):
        paths = resolved_rule_paths("lingyun", existing_only=True)
        self.assertGreaterEqual(len(paths), 3)
        for p in paths:
            self.assertTrue(p.is_file(), msg=str(p))

    def test_rules_by_layer(self):
        grouped = rules_by_layer("lingzhao")
        self.assertTrue(grouped["common"])
        self.assertTrue(grouped["frameworks"])
        self.assertTrue(grouped["roles"])

    def test_resolve_rule_path(self):
        p = resolve_rule_path("mailbus-core/rules/common/task-fsm.md")
        self.assertEqual(
            p.resolve(),
            (MAILBUS_ROOT / "rules" / "common" / "task-fsm.md").resolve(),
        )


if __name__ == "__main__":
    unittest.main()
