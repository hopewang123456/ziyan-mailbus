"""test_agent_card_gen — registry → Agent Card。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.transport.a2a_mapper import to_agent_card
from lib.transport.agent_card_cache import enrich_agent_channels, load_registry


class TestAgentCardGen(unittest.TestCase):
    def test_lingzhao_card_has_interface(self):
        registry = load_registry()
        entry = enrich_agent_channels("lingzhao", dict(registry.get("lingzhao") or {}))
        card = to_agent_card("lingzhao", entry, display_name="灵昭")
        self.assertEqual(card["metadata"]["mailbus"]["agent_id"], "lingzhao")
        self.assertTrue(card.get("supportedInterfaces"))

    def test_dali_card_no_interface(self):
        registry = load_registry()
        entry = enrich_agent_channels("dali", dict(registry.get("dali") or {}))
        card = to_agent_card("dali", entry, display_name="大力")
        self.assertEqual(card["metadata"]["mailbus"]["transport_default"], "file_bus")
        self.assertEqual(card.get("supportedInterfaces"), [])


if __name__ == "__main__":
    unittest.main()
