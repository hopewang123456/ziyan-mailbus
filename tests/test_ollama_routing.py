"""ollama_routing 单元测试"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.integrations.ollama_routing import (
    agent_supports_ollama,
    ollama_model_flag,
    resolve_ollama_settings,
)


AGENT_TYPES = {
    "models": {
        "ollama-local": {
            "hermes_profile": "--provider ollama --model {model}",
            "opencode": "--model ollama/{model}",
        }
    }
}


def test_resolve_ollama_settings_env():
    with patch.dict(os.environ, {"MAILBUS_OLLAMA_MODEL": "test:7b", "MAILBUS_OLLAMA_BASE_URL": "http://x:11434"}):
        s = resolve_ollama_settings()
    assert s["model"] == "test:7b"
    assert s["base_url"] == "http://x:11434"


def test_agent_supports_ollama():
    assert agent_supports_ollama({"type": "hermes_profile"}, AGENT_TYPES)
    assert not agent_supports_ollama({"type": "claude_code"}, AGENT_TYPES)


def test_ollama_model_flag():
    flag = ollama_model_flag(
        "hermes_profile",
        config=None,
        agent_types=AGENT_TYPES,
    )
    assert "ollama" in flag
    assert "qwen" in flag or "{model}" not in flag


if __name__ == "__main__":
    test_resolve_ollama_settings_env()
    test_agent_supports_ollama()
    test_ollama_model_flag()
    print("  all ollama_routing tests passed")
