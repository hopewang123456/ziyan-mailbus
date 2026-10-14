"""auth_policy unit tests."""

from __future__ import annotations

import tempfile
import unittest

from lib.adapters.config.auth_policy import (
    agent_requires_browser_auth,
    raw_browser_entry_url,
)
from lib.adapters.config import token_store
from lib.adapters.config.browser_auth import resolve_agent_auth


class TestAuthPolicy(unittest.TestCase):
    def test_requires(self):
        self.assertTrue(agent_requires_browser_auth("openclaw"))
        self.assertFalse(agent_requires_browser_auth("opencode"))
        self.assertTrue(agent_requires_browser_auth("claude_code", {"launch": {"has_browser": True}}))
        self.assertFalse(agent_requires_browser_auth("claude_code", {"launch": {"has_browser": False}}))

    def test_obtain_url_uses_host_port(self):
        url = raw_browser_entry_url(
            "store",
            "agent-a",
            {"type": "openclaw", "host": "10.0.0.2", "port": 18789},
        )
        self.assertIn("10.0.0.2", url)
        self.assertIn("18789", url)

    def test_ops0_style_openclaw_authed(self):
        with tempfile.TemporaryDirectory() as td:
            token_store.ensure_browser_credentials(td, "openclaw_gateway", mode="token", token="abc")
            out = resolve_agent_auth(
                {"type": "openclaw", "auth": {"mode": "token", "token_ref": "openclaw_gateway"}},
                "agent-a",
                td,
            )
            self.assertTrue(out.get("authed"))


if __name__ == "__main__":
    unittest.main()
