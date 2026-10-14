"""GPU coordinator tests."""

import json
import unittest
from unittest.mock import MagicMock, patch

from lib.adapters.integrations.gpu import (
    acquire_gpu,
    load_gpu_sharing_config,
    release_comfyui_vram,
    release_gpu,
    release_ollama_vram,
    reset_gpu_lock_for_tests,
)


class TestGpuSharingConfig(unittest.TestCase):
    def test_defaults_enabled(self):
        cfg = load_gpu_sharing_config({})
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["mode"], "time_share")

    def test_nested_in_internal_llm(self):
        cfg = load_gpu_sharing_config(
            {
                "mailbus_internal_llm": {
                    "gpu_sharing": {"enabled": False, "settle_seconds": 1},
                }
            }
        )
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["settle_seconds"], 1.0)


class TestGpuCoordinatorActions(unittest.TestCase):
    def setUp(self):
        reset_gpu_lock_for_tests()

    def tearDown(self):
        reset_gpu_lock_for_tests()

    @patch("lib.adapters.integrations.gpu._http_json")
    def test_release_ollama_vram(self, mock_http):
        mock_http.side_effect = [
            (True, {"models": [{"name": "qwen2.5:3b"}]}),
            (True, {}),
        ]
        out = release_ollama_vram("http://127.0.0.1:11434")
        self.assertTrue(out["ok"])
        self.assertEqual(out["released"], ["qwen2.5:3b"])

    @patch("lib.adapters.integrations.gpu._http_json")
    def test_release_comfyui_vram(self, mock_http):
        mock_http.return_value = (True, {"system": {}})
        out = release_comfyui_vram("http://127.0.0.1:8188")
        self.assertTrue(out["ok"])
        mock_http.assert_called_once()
        args = mock_http.call_args
        self.assertIn("/free", args[0][0])

    @patch("lib.adapters.integrations.gpu.release_ollama_vram")
    @patch("lib.adapters.integrations.gpu.time.sleep")
    def test_acquire_comfyui_unloads_ollama(self, _sleep, mock_release):
        mock_release.return_value = {"ok": True, "released": ["m1"]}
        cfg = {"gpu_sharing": {"enabled": True, "settle_seconds": 0}}
        out = acquire_gpu("comfyui", cfg)
        self.assertTrue(out["ok"])
        mock_release.assert_called_once()
        release_gpu("comfyui", cfg)

    def test_gpu_busy_second_owner(self):
        cfg = {"gpu_sharing": {"enabled": True, "settle_seconds": 0, "release_ollama_before_image": False}}
        with patch("lib.adapters.integrations.gpu.release_comfyui_vram"):
            acquire_gpu("comfyui", cfg)
            busy = acquire_gpu("ollama", cfg)
            self.assertFalse(busy["ok"])
            self.assertEqual(busy["error"], "gpu_busy")
            release_gpu("comfyui", cfg)


if __name__ == "__main__":
    unittest.main()
