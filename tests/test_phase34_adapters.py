"""Phase 3.4 — access adapters, agentmemory config, init-store launch tests."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.config.access_adapters import (
    adapter_spec_path,
    load_adapter_spec,
    validate_access_adapters,
)
from lib.adapters.frameworks import framework_adapter_spec
from lib.adapters.integrations.agentmemory_config import (
    agentmemory_url,
    load_integration_config,
    pending_dir,
    team_memory_db_path,
)
from lib.infra.constants import MAILBUS_ROOT
from lib.infra.utils import to_wsl_path
from lib.adapters.config.init_store import build_agent_entry, run_init_store
from lib.adapters.container.privilege import _host_path_under_mailbus, _to_container_mailbus_path
from lib.adapters.config.sync_layers import dashboard_skills_dirs


class TestAccessAdapters(unittest.TestCase):
    def test_hermes_profile_spec_exists(self):
        spec = adapter_spec_path("hermes_profile")
        self.assertTrue(spec.is_file(), msg=str(spec))
        text = load_adapter_spec("hermes_profile")
        self.assertIn("hermes_profile", text.lower())

    def test_validate_all_frameworks(self):
        errors = validate_access_adapters(mail_root=MAILBUS_ROOT)
        self.assertEqual(errors, [], msg=str(errors))

    def test_agent_adapters_wrapper(self):
        text = framework_adapter_spec("codex")
        self.assertIn("codex", text.lower())


class TestAgentmemoryConfig(unittest.TestCase):
    def test_integration_json_loads(self):
        cfg = load_integration_config(str(MAILBUS_ROOT))
        self.assertEqual(cfg.get("schema"), "mailbus-agentmemory-v1")
        self.assertIn("bridge", cfg)

    def test_pending_dir_under_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pending_dir(tmp, mail_root=MAILBUS_ROOT)
            self.assertTrue(str(p).replace("\\", "/").endswith("agentmemory-pending"))

    def test_team_memory_db_configured(self):
        path = team_memory_db_path(mail_root=MAILBUS_ROOT)
        self.assertIn("team-memory.db", path)


class TestPrivilegePaths(unittest.TestCase):
    def test_mailbus_host_path_native(self):
        native = str(MAILBUS_ROOT / "store" / "config.json")
        self.assertTrue(_host_path_under_mailbus(native))

    def test_container_path_mapping(self):
        wsl = to_wsl_path(str(MAILBUS_ROOT / "store" / "config.json"))
        self.assertTrue(_host_path_under_mailbus(wsl))
        cp = _to_container_mailbus_path(wsl)
        self.assertEqual(cp, "/mailbus/store/config.json")


class TestInitStoreLaunch(unittest.TestCase):
    def _any_agent(self, registry):
        return sorted(registry)[0] if registry else None

    def test_first_registry_agent_has_launch_and_profile_paths(self):
        from lib.adapters.config.agent_registry import get_agent, clear_agent_registry_cache

        clear_agent_registry_cache()
        registry = _registry()
        aid = self._any_agent(registry)
        if aid is None:
            self.skipTest("no agents configured (open-source default)")
        rec = get_agent(aid)
        self.assertIsNotNone(rec)
        from lib.adapters.config.init_store import load_config_fragments, load_roster

        fragments = load_config_fragments(mail_root=MAILBUS_ROOT)
        overrides = fragments.get("_agent_overrides") or {}
        entry = build_agent_entry(
            aid,
            rec,
            load_roster(MAILBUS_ROOT).get(aid),
            data_dir="/tmp/store",
            override=overrides.get(aid),
        )
        self.assertIn("launch", entry)
        self.assertIn("profile_paths", entry)
        self.assertIn("template", entry["launch"])

    def test_fresh_init_generates_launch_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = run_init_store(tmp, fresh=True, mail_root=MAILBUS_ROOT, quiet=True)
            self.assertEqual(rc, 0)
            import json

            cfg = json.load(open(os.path.join(tmp, "config.json"), encoding="utf-8"))
            agents = cfg.get("agents") or {}
            self.assertGreaterEqual(len(agents), 1)
            with_launch = [a for a in agents.values() if a.get("launch")]
            with_profile = [a for a in agents.values() if a.get("profile_paths")]
            self.assertGreaterEqual(len(with_launch), 1)
            self.assertGreaterEqual(len(with_profile), 1)


def _registry():
    from lib.adapters.config.agent_registry import load_all_agents

    return load_all_agents(mail_root=MAILBUS_ROOT, refresh=True)


class TestDashboardSkillsDirs(unittest.TestCase):
    def test_registry_covers_core_agents(self):
        dirs = dashboard_skills_dirs(mail_root=MAILBUS_ROOT)
        agents = sorted(_registry().keys())
        if not agents:
            self.skipTest("no agents configured (open-source default)")
        for aid in agents[:4]:
            self.assertIn(aid, dirs, msg=f"missing skills dir for {aid}")


if __name__ == "__main__":
    unittest.main()
