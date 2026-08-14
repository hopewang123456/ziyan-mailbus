"""test_agent_card_gen — registry → Agent Card。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.core.a2a.a2a_mapper import to_agent_card
from lib.core.a2a.agent_card_cache import enrich_agent_channels, load_registry


class TestAgentCardGen(unittest.TestCase):
    def test_hermes_card_has_interface(self):
        registry = load_registry()
        hermes = [
            aid for aid, e in registry.items()
            if (e.get("framework") or "").startswith("hermes")
        ]
        if not hermes:
            self.skipTest("no hermes agent in registry")
        aid = hermes[0]
        entry = enrich_agent_channels(aid, dict(registry.get(aid) or {}))
        card = to_agent_card(aid, entry, display_name="Agent X")
        self.assertEqual(card["metadata"]["mailbus"]["agent_id"], aid)
        self.assertTrue(card.get("supportedInterfaces"))

    def test_opencode_card_no_interface(self):
        registry = load_registry()
        opencode = [
            aid for aid, e in registry.items()
            if e.get("framework") == "opencode"
        ]
        if not opencode:
            self.skipTest("no opencode agent in registry")
        aid = opencode[0]
        entry = enrich_agent_channels(aid, dict(registry.get(aid) or {}))
        card = to_agent_card(aid, entry, display_name="Agent X")
        self.assertEqual(card["metadata"]["mailbus"]["transport_default"], "file_bus")
        self.assertEqual(card.get("supportedInterfaces"), [])


if __name__ == "__main__":
    unittest.main()
