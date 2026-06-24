"""Tests for lib.internal_llm.ollama_ensure."""

import sys
import unittest
from unittest.mock import MagicMock, patch

try:
    import fcntl  # noqa: F401
except ImportError:
    sys.modules["fcntl"] = MagicMock()

from lib.internal_llm.ollama_ensure import ensure_ollama, model_present


class TestOllamaEnsure(unittest.TestCase):
    def test_model_present(self):
        self.assertTrue(model_present(["qwen2.5:3b-instruct-q4_K_M"], "qwen2.5:3b-instruct-q4_K_M"))
        self.assertFalse(model_present(["llama3:8b"], "qwen2.5:3b-instruct-q4_K_M"))

    @patch("lib.internal_llm.ollama_ensure.probe_tags")
    def test_ensure_already_ready(self, mock_probe):
        mock_probe.return_value = (True, ["qwen2.5:3b-instruct-q4_K_M"])
        out = ensure_ollama("http://127.0.0.1:11434", "qwen2.5:3b-instruct-q4_K_M", start=False, pull=False)
        self.assertTrue(out["ok"])
        self.assertTrue(out["model_available"])

    @patch("lib.internal_llm.ollama_ensure.pull_model", return_value=True)
    @patch("lib.internal_llm.ollama_ensure.probe_tags")
    def test_ensure_pulls_missing_model(self, mock_probe, _mock_pull):
        mock_probe.side_effect = [
            (True, []),
            (True, ["qwen2.5:3b-instruct-q4_K_M"]),
        ]
        with patch("lib.internal_llm.ollama_ensure.find_ollama_bin", return_value="/usr/bin/ollama"):
            out = ensure_ollama("http://127.0.0.1:11434", "qwen2.5:3b-instruct-q4_K_M", start=False, pull=True)
        self.assertTrue(out["ok"])


if __name__ == "__main__":
    unittest.main()
