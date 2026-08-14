"""CredDelivery + agent_instances synthesize tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from lib.adapters.config.agent_instances import synthesize_instances_from_agents
from lib.adapters.config import token_store
from lib.adapters.runtime.cred_delivery import (
    apply_instance_endpoint,
    resolve_openclaw_token,
    sync_browser_credentials_to_env,
)


class TestCredDelivery(unittest.TestCase):
    def test_sync_openclaw_from_secrets(self):
        with tempfile.TemporaryDirectory() as td:
            token_store.ensure_browser_credentials(td, "openclaw_gateway", mode="token", token="test-oc-token")
            os.environ.pop("OPENCLAW_GATEWAY_TOKEN", None)
            applied = sync_browser_credentials_to_env(td)
            self.assertIn("OPENCLAW_GATEWAY_TOKEN", applied)
            self.assertEqual(os.environ.get("OPENCLAW_GATEWAY_TOKEN"), "test-oc-token")
            self.assertEqual(resolve_openclaw_token(td), "test-oc-token")
            os.environ.pop("OPENCLAW_GATEWAY_TOKEN", None)

    def test_apply_instance_endpoint(self):
        url = apply_instance_endpoint(
            {"host": "172.28.1.2", "port": 9120},
            "http://127.0.0.1:9999/chat",
        )
        self.assertEqual(url, "http://172.28.1.2:9120/chat")


class TestAgentInstances(unittest.TestCase):
    def test_synthesize_groups_same_type_path(self):
        cfg = {
            "agents": {
                "a": {"type": "hermes_profile", "run_target": "windows", "install_path": "E:/h"},
                "b": {"type": "hermes_profile", "run_target": "windows", "install_path": "E:/h"},
                "c": {"type": "openclaw", "run_target": "windows", "install_path": "E:/oc"},
            }
        }
        out = synthesize_instances_from_agents(cfg)
        inst = out["agent_instances"]
        self.assertEqual(len(inst), 2)
        hermes_ids = [i for i in inst.values() if i["type"] == "hermes_profile"]
        self.assertEqual(len(hermes_ids), 1)
        self.assertEqual(set(hermes_ids[0]["role_ids"]), {"a", "b"})
        self.assertEqual(out["agents"]["a"]["instance_id"], hermes_ids[0]["id"])

    def test_synthesize_merges_roles_despite_different_ports(self):
        cfg = {
            "agents": {
                "agent-a": {
                    "type": "hermes_profile",
                    "run_target": "docker",
                    "install_path": "E:/h",
                    "host": "127.0.0.1",
                    "port": 9120,
                },
                "agent-b": {
                    "type": "hermes_profile",
                    "run_target": "docker",
                    "install_path": "E:/h",
                    "host": "localhost",
                    "port": 9121,
                },
            },
            "agent_instances": {
                "inst-a": {
                    "id": "inst-a",
                    "type": "hermes_profile",
                    "run_target": "docker",
                    "install_path": "E:/h",
                    "host": "127.0.0.1",
                    "port": 9120,
                    "role_ids": ["agent-a"],
                },
                "inst-b": {
                    "id": "inst-b",
                    "type": "hermes_profile",
                    "run_target": "docker",
                    "install_path": "E:\\h",
                    "host": "127.0.0.1",
                    "port": 9121,
                    "role_ids": ["agent-b"],
                },
            },
        }
        out = synthesize_instances_from_agents(cfg)
        hermes = [i for i in out["agent_instances"].values() if i["type"] == "hermes_profile"]
        self.assertEqual(len(hermes), 1)
        self.assertEqual(set(hermes[0]["role_ids"]), {"agent-a", "agent-b"})
        self.assertEqual(out["agents"]["agent-a"]["instance_id"], hermes[0]["id"])
        self.assertEqual(out["agents"]["agent-b"]["instance_id"], hermes[0]["id"])


if __name__ == "__main__":
    unittest.main()
