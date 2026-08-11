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

    def test_loopback_write_without_token(self):
        with tempfile.TemporaryDirectory() as td:
            ensure_token(td)
            ctx = ClientContext(remote_addr="127.0.0.1")
            self.assertEqual(authorize_write(td, ctx), AuthDecision.ALLOW)

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


if __name__ == "__main__":
    unittest.main()
