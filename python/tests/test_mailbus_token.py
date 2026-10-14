# tests for Mailbus token auth rules
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lib.application.mailbus_token import authorize_write, ensure_token, rotate_token
from lib.domain.types import AuthDecision, ClientContext


class TestMailbusToken(unittest.TestCase):
    def test_ensure_and_resolve(self):
        with tempfile.TemporaryDirectory() as td:
            t1 = ensure_token(td)
            t2 = ensure_token(td)
            self.assertEqual(t1, t2)
            self.assertTrue((Path(td) / "secrets.json").is_file())

    def test_loopback_write_requires_token_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            tok = ensure_token(td)
            ctx = ClientContext(remote_addr="127.0.0.1")
            self.assertEqual(authorize_write(td, ctx), AuthDecision.DENY)
            ok = ClientContext(remote_addr="127.0.0.1", authorization=f"Bearer {tok}")
            self.assertEqual(authorize_write(td, ok), AuthDecision.ALLOW)

    def test_loopback_free_when_flag_and_default_cidrs(self):
        with tempfile.TemporaryDirectory() as td:
            ensure_token(td)
            cfg = {"auth": {"allow_write_without_token": True}}
            self.assertEqual(
                authorize_write(td, ClientContext(remote_addr="127.0.0.1"), config=cfg),
                AuthDecision.ALLOW,
            )

    def test_wsl_cidr_when_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            ensure_token(td)
            cfg = {
                "auth": {
                    "allow_write_without_token": True,
                    "write_without_token_cidrs": ["172.16.0.0/12", "127.0.0.1/32"],
                }
            }
            self.assertEqual(
                authorize_write(td, ClientContext(remote_addr="172.20.5.1"), config=cfg),
                AuthDecision.ALLOW,
            )
            self.assertEqual(
                authorize_write(td, ClientContext(remote_addr="10.0.0.2"), config=cfg),
                AuthDecision.DENY,
            )

    def test_remote_requires_token(self):
        with tempfile.TemporaryDirectory() as td:
            tok = ensure_token(td)
            bad = ClientContext(remote_addr="192.168.1.10")
            self.assertEqual(authorize_write(td, bad), AuthDecision.DENY)
            good = ClientContext(remote_addr="192.168.1.10", authorization=f"Bearer {tok}")
            self.assertEqual(authorize_write(td, good), AuthDecision.ALLOW)

    def test_remote_rotate_requires_old(self):
        with tempfile.TemporaryDirectory() as td:
            old = ensure_token(td)
            ctx = ClientContext(remote_addr="10.0.0.2")
            denied = rotate_token(td, ctx)
            self.assertFalse(denied.get("ok"))
            ok = rotate_token(td, ClientContext(remote_addr="10.0.0.2", authorization=f"Bearer {old}"))
            self.assertTrue(ok.get("ok"))
            self.assertNotEqual(ok.get("token"), old)

    def test_exempt_cidrs_alias_requires_flag(self):
        """legacy exempt_cidrs 并入白名单，但仍需 allow_write_without_token。"""
        with tempfile.TemporaryDirectory() as td:
            ensure_token(td)
            cfg_off = {"auth": {"exempt_cidrs": ["10.0.0.0/8"]}}
            self.assertEqual(
                authorize_write(td, ClientContext(remote_addr="10.0.0.2"), config=cfg_off),
                AuthDecision.DENY,
            )
            cfg_on = {"auth": {"allow_write_without_token": True, "exempt_cidrs": ["10.0.0.0/8"]}}
            self.assertEqual(
                authorize_write(td, ClientContext(remote_addr="10.0.0.2"), config=cfg_on),
                AuthDecision.ALLOW,
            )

    def test_exempt_cidrs_top_level_with_flag(self):
        with tempfile.TemporaryDirectory() as td:
            ensure_token(td)
            cfg = {"auth": {"allow_write_without_token": True}, "exempt_cidrs": "192.168.50.10"}
            self.assertEqual(
                authorize_write(td, ClientContext(remote_addr="192.168.50.10"), config=cfg),
                AuthDecision.ALLOW,
            )
            self.assertEqual(
                authorize_write(td, ClientContext(remote_addr="192.168.50.11"), config=cfg),
                AuthDecision.DENY,
            )


if __name__ == "__main__":
    unittest.main()
