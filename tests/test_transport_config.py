"""Transport 配置加载 — template 嵌套 merge 与 streaming 开关。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.infra.constants import MAILBUS_ROOT
from lib.adapters.config.init_store import build_store_config, load_config_fragments
from lib.core.a2a.config import load_transport_config, resolve_use_streaming
from lib.infra.utils import json_read, json_write


class TestLoadTransportConfig(unittest.TestCase):
    def test_template_exposes_use_streaming_and_stream_defaults(self):
        cfg = load_transport_config()
        a2a = cfg.get("a2a") or {}
        self.assertNotIn(
            "async_dispatch",
            a2a,
            "transport.template.json 不应含 async_dispatch（仅 scanner 路径，见 _doc）",
        )
        self.assertIn("use_streaming", a2a, "transport.template.json transport.a2a.use_streaming 应可见")
        self.assertIs(a2a.get("use_streaming"), False)
        self.assertEqual(a2a.get("stream_poll_sec"), 0.1)
        self.assertEqual(a2a.get("stream_timeout_sec"), 120)
        self.assertEqual(a2a.get("stream_heartbeat_sec"), 15)

    def test_store_transport_overrides_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_write(
                os.path.join(tmp, "config.json"),
                {"transport": {"a2a": {"use_streaming": True, "stream_poll_sec": 0.5}}},
            )
            cfg = load_transport_config(data_dir=tmp)
            a2a = cfg["a2a"]
            self.assertTrue(a2a["use_streaming"])
            self.assertEqual(a2a["stream_poll_sec"], 0.5)

    def test_inline_config_overrides_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_write(
                os.path.join(tmp, "config.json"),
                {"transport": {"a2a": {"use_streaming": False}}},
            )
            cfg = load_transport_config(
                config={"transport": {"a2a": {"use_streaming": True}}},
                data_dir=tmp,
            )
            self.assertTrue(cfg["a2a"]["use_streaming"])

    def test_defaults_preserved_when_template_partial(self):
        cfg = load_transport_config()
        a2a = cfg["a2a"]
        self.assertEqual(a2a.get("max_retries"), 3)
        self.assertEqual(a2a.get("stream_poll_sec"), 0.1)


class TestResolveUseStreaming(unittest.TestCase):
    def test_agent_override_wins(self):
        cfg = {"transport": {"a2a": {"use_streaming": False}}}
        agent = {"channels": {"a2a": {"use_streaming": True}}}
        self.assertTrue(resolve_use_streaming(cfg, agent))

    def test_global_from_loaded_template(self):
        cfg = {"transport": load_transport_config()}
        self.assertFalse(resolve_use_streaming(cfg))


class TestHarnessProductionProfile(unittest.TestCase):
    def test_harness_template_production_use_router(self):
        harness_tpl = json_read(
            str(MAILBUS_ROOT / "config" / "mailbus" / "harness.template.json"), {},
        )
        self.assertEqual((harness_tpl.get("harness") or {}).get("mode"), "production")
        self.assertTrue((harness_tpl.get("transport") or {}).get("use_router"))

    def test_load_config_fragments_merges_harness_transport(self):
        fragments = load_config_fragments(mail_root=MAILBUS_ROOT)
        self.assertEqual((fragments.get("harness") or {}).get("mode"), "production")
        self.assertTrue((fragments.get("transport") or {}).get("use_router"))

    def test_build_store_config_use_router_from_harness_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = build_store_config(data_dir=tmp, mail_root=MAILBUS_ROOT)
            self.assertTrue((cfg.get("transport") or {}).get("use_router"))
            self.assertEqual((cfg.get("harness") or {}).get("mode"), "production")


if __name__ == "__main__":
    tpl = MAILBUS_ROOT / "config" / "mailbus" / "transport.template.json"
    if not tpl.is_file():
        raise SystemExit(f"missing template: {tpl}")
    unittest.main()
