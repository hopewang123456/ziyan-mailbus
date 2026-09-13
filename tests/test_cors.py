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


if __name__ == "__main__":
    unittest.main()
