"""模型 Provider 标准化视图 — 合并 / protocol 归一 / api_key_configured / 掩码 / anthropic。"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.adapters.internal_llm.config_resolve import (
    _api_key_configured,
    _normalize_protocol,
    provider_view,
)
from lib.adapters.config.config_schema import validate_config
from lib.adapters.internal_llm.probe import probe_provider
from lib.adapters.internal_llm import client as client_mod


class TestProviderView(unittest.TestCase):
    def test_merges_seed_providers(self):
        v = provider_view({"enabled": True}, "")
        provs = v["providers"]
        self.assertIn("local", provs)
        self.assertIn("remote", provs)
        self.assertIn("claude", provs)
        self.assertIn("stub", provs)
        self.assertEqual(provs["local"]["protocol"], "ollama")
        self.assertEqual(provs["remote"]["protocol"], "openai")
        self.assertEqual(provs["claude"]["protocol"], "anthropic")
        self.assertEqual(provs["stub"]["protocol"], "stub")

    def test_store_overrides_seed(self):
        raw = {
            "providers": {
                "remote": {"protocol": "openai", "model": "deepseek-reasoner", "base_url": "https://x/v1"},
            }
        }
        v = provider_view(raw, "")
        self.assertEqual(v["providers"]["remote"]["model"], "deepseek-reasoner")

    def test_protocol_normalize_legacy_kind(self):
        self.assertEqual(_normalize_protocol({"kind": "openai_compatible"}, "x"), "openai")
        self.assertEqual(_normalize_protocol({"kind": "ollama"}, "x"), "ollama")
        self.assertEqual(_normalize_protocol({"kind": "anthropic"}, "x"), "anthropic")
        self.assertEqual(_normalize_protocol({}, "stub"), "stub")
        self.assertEqual(_normalize_protocol({}, "remote"), "openai")

    def test_api_key_configured_from_env(self):
        with mock.patch.dict(os.environ, {"MAILBUS_INTERNAL_LLM_API_KEY": "sk-test"}):
            self.assertTrue(_api_key_configured({"api_key_env": "MAILBUS_INTERNAL_LLM_API_KEY"}))
        # 负例：显式清掉该变量再断言，避免其它测试（如 load_mailbus_env）泄漏 .env 值污染环境
        with mock.patch.dict(os.environ):
            os.environ.pop("MAILBUS_INTERNAL_LLM_API_KEY", None)
            self.assertFalse(_api_key_configured({"api_key_env": "MAILBUS_INTERNAL_LLM_API_KEY"}))

    def test_api_key_masked(self):
        v = provider_view({"providers": {"remote": {"protocol": "openai", "api_key": "sk-secret"}}}, "")
        self.assertEqual(v["providers"]["remote"]["api_key"], "***")
        self.assertTrue(v["providers"]["remote"]["api_key_configured"])

    def test_validate_protocol_enum(self):
        base = {
            "project": "p", "version": "1.0.0", "data_dir": "d",
            "ack_timeout": 30, "max_retries": 3, "archive_days": 3,
            "archive_max_messages": 300, "agents": {},
        }
        ok = dict(base)
        ok["mailbus_internal_llm"] = {"providers": {"r": {"protocol": "openai"}}}
        self.assertEqual(validate_config(ok), [])
        bad = dict(base)
        bad["mailbus_internal_llm"] = {"providers": {"r": {"protocol": "gemini"}}}
        errs = validate_config(bad)
        self.assertTrue(any("protocol" in e for e in errs))

    def test_probe_anthropic_missing_env(self):
        out = probe_provider("claude", {"protocol": "anthropic", "api_key_env": "ANTHROPIC_API_KEY"})
        self.assertFalse(out["ok"])
        self.assertIn("missing env", out["error"])


class TestAnthropicClient(unittest.TestCase):
    def test_anthropic_complete(self):
        fake_resp = mock.MagicMock()
        fake_resp.read.return_value = json.dumps(
            {"content": [{"type": "text", "text": '{"ok":1}'}]}
        ).encode()
        fake_resp.__enter__.return_value = fake_resp
        fake_resp.__exit__.return_value = False
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant"}):
            with mock.patch.object(client_mod.urllib.request, "urlopen", return_value=fake_resp) as m:
                text = client_mod._anthropic_complete(
                    [
                        {"role": "system", "content": "sys"},
                        {"role": "user", "content": "hi"},
                    ],
                    {"protocol": "anthropic", "model": "claude-sonnet-4-5"},
                )
        self.assertEqual(text, '{"ok":1}')
        req = m.call_args.args[0]
        self.assertIn("/v1/messages", req.full_url)
        self.assertEqual(req.headers.get("X-api-key"), "sk-ant")
        body = json.loads(req.data.decode())
        self.assertEqual(body["system"], "sys")
        self.assertEqual(body["messages"], [{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
