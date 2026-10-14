"""Ops0 / browser_auth card resolution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lib.adapters.config.browser_auth import resolve_agent_auth
from lib.adapters.config import token_store


class TestHermesCardSession(unittest.TestCase):
    def test_hermes_token_ref_authed_without_url_mode(self):
        with tempfile.TemporaryDirectory() as td:
            token_store.ensure_browser_credentials(td, "hermes", mode="token")
            cfg = {
                "type": "hermes_profile",
                "auth": {"mode": "token", "token_ref": "hermes"},
            }
            out = resolve_agent_auth(cfg, "agent-a", td)
            self.assertTrue(out.get("authed"))
            self.assertTrue(out.get("session"))
            self.assertEqual(out.get("mode"), "none")
            self.assertTrue((out.get("token") or "").strip())


class TestCodexCardBasic(unittest.TestCase):
    def test_codex_basic_ref(self):
        with tempfile.TemporaryDirectory() as td:
            token_store.ensure_browser_credentials(td, "agent-b", mode="basic")
            cfg = {
                "type": "codex",
                "auth": {
                    "mode": "basic",
                    "username_ref": "agent-b",
                    "password_ref": "agent-b",
                },
            }
            out = resolve_agent_auth(cfg, "agent-b", td)
            self.assertTrue(out.get("authed"))
            self.assertEqual(out.get("mode"), "basic")


if __name__ == "__main__":
    unittest.main()
