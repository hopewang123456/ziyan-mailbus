"""ComfyUI client tests."""

import unittest

from lib.comfyui.client import _build_sd15_workflow, health_check


class TestComfyuiClient(unittest.TestCase):
    def test_workflow_shape(self):
        wf = _build_sd15_workflow(
            prompt="test", negative="bad", ckpt="model.safetensors",
            width=512, height=512, steps=20, cfg=7.0, seed=1,
        )
        self.assertIn("4", wf)
        self.assertEqual(wf["4"]["class_type"], "CheckpointLoaderSimple")

    def test_health_unreachable(self):
        ok, _ = health_check("http://127.0.0.1:1")
        self.assertFalse(ok)

    def test_url_resolve_candidates(self):
        from lib.comfyui.url_resolve import _candidate_urls

        urls = _candidate_urls("http://custom:8188")
        self.assertEqual(urls[0], "http://custom:8188")
        self.assertIn("http://127.0.0.1:8188", urls)


if __name__ == "__main__":
    unittest.main()
