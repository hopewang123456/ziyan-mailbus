"""Internal LLM probe tests."""
import contextlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("fcntl", MagicMock())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lib.utils as _utils


@contextlib.contextmanager
def _noop_file_lock(timeout=10.0, path=""):
    yield


_utils.file_lock = _noop_file_lock

from lib.internal_llm.probe import probe_provider


class TestLlmProbe(unittest.TestCase):
    def test_stub_provider_ok(self):
        r = probe_provider("stub", {"kind": "stub"})
        self.assertTrue(r["ok"])

    def test_ollama_unreachable(self):
        r = probe_provider("local", {"kind": "ollama", "base_url": "http://127.0.0.1:59999"})
        self.assertFalse(r["ok"])

    @patch.dict(os.environ, {"MAILBUS_INTERNAL_LLM_API_KEY": "test-key"})
    @patch("urllib.request.urlopen")
    def test_remote_ok(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.read.return_value = b'{}'
        r = probe_provider("remote", {
            "kind": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key_env": "MAILBUS_INTERNAL_LLM_API_KEY",
        })
        self.assertTrue(r["ok"])


if __name__ == "__main__":
    unittest.main()
