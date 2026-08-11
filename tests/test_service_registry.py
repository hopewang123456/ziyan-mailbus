"""service_registry unit tests."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib.adapters.ops.service_registry import (
    compose_env_for_services,
    detect_runtime,
    service_settings,
    service_url,
)


class TestServiceRegistry(unittest.TestCase):
    def test_seed_profiles_resolve(self):
        win = service_settings("ollama", runtime="windows", ignore_env=True)
        self.assertIn("11434", win["base_url"])
        docker = service_settings("ollama", runtime="docker", ignore_env=True)
        self.assertIn("host.docker.internal", docker["base_url"])
        am = service_url("agentmemory", runtime="docker", ignore_env=True)
        self.assertIn("iii-engine", am)

    def test_compose_env_ignores_host_localhost(self):
        with mock.patch.dict(
            os.environ,
            {
                "MAILBUS_OLLAMA_BASE_URL": "http://127.0.0.1:11434",
                "AGENTMEMORY_URL": "http://127.0.0.1:3111",
            },
            clear=False,
        ):
            env = compose_env_for_services()
        self.assertIn("host.docker.internal", env["MAILBUS_OLLAMA_BASE_URL"])
        self.assertIn("iii-engine", env["AGENTMEMORY_URL"])
        self.assertNotIn("127.0.0.1", env["MAILBUS_OLLAMA_BASE_URL"])

    def test_env_override_when_not_ignored(self):
        with mock.patch.dict(
            os.environ,
            {"MAILBUS_OLLAMA_BASE_URL": "http://custom:9999"},
            clear=False,
        ):
            s = service_settings("ollama", runtime="windows", ignore_env=False)
        self.assertEqual(s["base_url"], "http://custom:9999")

    def test_detect_runtime_windows(self):
        if os.name == "nt":
            with mock.patch("lib.adapters.ops.service_registry.detect_runtime", wraps=detect_runtime):
                # Just ensure callable; on Windows host expect windows unless docker
                rt = detect_runtime()
                self.assertIn(rt, ("windows", "wsl", "docker"))


class TestOllamaLocalDrift(unittest.TestCase):
    def test_ensure_ollama_local_alias(self):
        from lib.adapters.config.init_store import ensure_ollama_local_model_alias

        cfg = {"smart_routing": {"enabled": True, "use_ollama": True}, "agent_types": {"models": {}}}
        changed = ensure_ollama_local_model_alias(cfg)
        self.assertTrue(changed)
        self.assertIn("ollama-local", cfg["agent_types"]["models"])
        self.assertFalse(ensure_ollama_local_model_alias(cfg))


if __name__ == "__main__":
    unittest.main()
