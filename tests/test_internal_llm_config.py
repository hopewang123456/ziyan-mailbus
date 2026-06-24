"""config_resolve 双 provider 解析。"""
import os
import sys
import unittest
from unittest import mock
from unittest.mock import MagicMock

sys.modules.setdefault("fcntl", MagicMock())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.internal_llm.config_resolve import resolve_llm_config, resolve_provider


class TestConfigResolve(unittest.TestCase):
    def test_default_priority_local_remote(self):
        cfg = resolve_llm_config({"enabled": True, "providers": {"local": {"kind": "ollama"}, "remote": {}}})
        self.assertEqual(cfg["provider_priority"], ["local", "remote"])

    @mock.patch.dict(os.environ, {"MAILBUS_OLLAMA_BASE_URL": "http://192.168.1.10:11434"})
    def test_ollama_base_url_env(self):
        pc = resolve_provider("local", {"kind": "ollama", "base_url": "http://127.0.0.1:11434"})
        self.assertEqual(pc["base_url"], "http://192.168.1.10:11434")

    @mock.patch.dict(os.environ, {"MAILBUS_INTERNAL_LLM_PROVIDER_PRIORITY": "remote,local"})
    def test_priority_env_override(self):
        cfg = resolve_llm_config({
            "providers": {"local": {}, "remote": {}},
        })
        self.assertEqual(cfg["provider_priority"], ["remote", "local"])


if __name__ == "__main__":
    unittest.main()
