"""CORS 白名单单元测试。"""
from __future__ import annotations

import unittest

from lib.infra.cors import pick_cors_origin


class TestCors(unittest.TestCase):
    def test_empty_whitelist_blocks_star(self):
        self.assertIsNone(pick_cors_origin("http://evil.test", {}))
        self.assertIsNone(pick_cors_origin("http://evil.test", {"auth": {}}))

    def test_explicit_origin(self):
        cfg = {"auth": {"cors_origins": ["http://localhost:5173"]}}
        self.assertEqual(
            pick_cors_origin("http://localhost:5173", cfg),
            "http://localhost:5173",
        )
        self.assertIsNone(pick_cors_origin("http://evil.test", cfg))

    def test_star_reflects_origin(self):
        cfg = {"auth": {"cors_origins": ["*"]}}
        self.assertEqual(pick_cors_origin("http://app.test", cfg), "http://app.test")
        self.assertEqual(pick_cors_origin("", cfg), "*")

    def test_api_handlers_do_not_hardcode_star(self):
        from pathlib import Path

        api = Path(__file__).resolve().parents[1] / "lib" / "api"
        hits = []
        needle = 'Access-Control-Allow-Origin", "*"'
        needle2 = "Access-Control-Allow-Origin', '*'"
        for p in api.glob("*.py"):
            text = p.read_text(encoding="utf-8")
            if needle in text or needle2 in text:
                hits.append(p.name)
        self.assertEqual(hits, [], msg=f"hardcoded CORS *: {hits}")


if __name__ == "__main__":
    unittest.main()
