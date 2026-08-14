"""agent-demo.json: demo roster seed validity + no personal data."""
from __future__ import annotations

import unittest

from lib.infra.agent_demo import (
    hermes_demo_agents,
    hermes_demo_dashboards,
    openclaw_gateway_ports,
    openclaw_state_dirs,
    pipeline_full_agents,
    pipeline_legacy_agent_role,
    pipeline_role_flow,
    validate_agent_demo,
)


class TestAgentDemoSeed(unittest.TestCase):
    def test_demo_json_valid(self) -> None:
        self.assertEqual(validate_agent_demo(), [])

    def test_demo_roster_is_generic(self) -> None:
        for aid in hermes_demo_agents():
            self.assertRegex(aid, r"^agent-[a-z0-9]+$", msg=f"non-generic id: {aid}")
        for aid in pipeline_full_agents():
            self.assertRegex(aid, r"^agent-[a-z0-9]+$", msg=f"non-generic id: {aid}")

    def test_openclaw_maps_consistent(self) -> None:
        state_keys = set(openclaw_state_dirs())
        port_keys = set(openclaw_gateway_ports())
        self.assertTrue(port_keys.issubset(state_keys) or state_keys.issubset(port_keys),
                        msg=f"state/port keys diverge: {state_keys} vs {port_keys}")

    def test_dashboards_have_unique_ports(self) -> None:
        dash = hermes_demo_dashboards()
        ports = [p for _, p in dash]
        self.assertEqual(len(ports), len(set(ports)), msg=f"duplicate ports: {ports}")

    def test_role_flow_keys_have_separator(self) -> None:
        for key in pipeline_role_flow():
            self.assertIn("|", key, msg=f"role_flow key missing '|': {key}")
            self.assertTrue(key.split("|", 1)[0].strip(), msg=f"empty role in {key!r}")

    def test_legacy_roles_use_generic_ids(self) -> None:
        for aid in pipeline_legacy_agent_role():
            self.assertRegex(aid, r"^agent-[a-z0-9]+$", msg=f"non-generic id: {aid}")


if __name__ == "__main__":
    unittest.main()
