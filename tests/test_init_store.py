"""Phase 3 — init-store tests."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.config.config_schema import validate_config
from lib.adapters.config.init_store import (
    build_agents_from_registry,
    build_store_config,
    load_config_fragments,
    mirror_org_json,
    run_init_store,
    run_merge_store_config,
)
from lib.infra.constants import MAILBUS_ROOT


class TestInitStore(unittest.TestCase):
    def test_load_config_fragments_has_scheduler(self):
        fragments = load_config_fragments(mail_root=MAILBUS_ROOT)
        self.assertIn("scheduler", fragments)
        self.assertIn("jobs", fragments["scheduler"])

    def test_load_config_fragments_has_decomposition(self):
        fragments = load_config_fragments(mail_root=MAILBUS_ROOT)
        decomp = (fragments.get("pipeline_ops") or {}).get("decomposition")
        self.assertIsInstance(decomp, dict)
        self.assertIn("design_role_types", decomp)

    def test_load_config_fragments_has_quality_harness(self):
        fragments = load_config_fragments(mail_root=MAILBUS_ROOT)
        post = (fragments.get("quality_harness") or {}).get("post_commit") or {}
        self.assertEqual(post.get("trusted_source"), "post-commit-harness")
        self.assertTrue(post.get("publish_on_warn_fail"))

    def test_build_agents_from_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents = build_agents_from_registry(data_dir=tmp, mail_root=MAILBUS_ROOT)
            self.assertGreaterEqual(len(agents), 1)
            opencode = next((a for a in agents.values() if a.get("type") == "opencode"), None)
            if opencode is None:
                self.skipTest("no opencode agent configured")
            self.assertEqual(opencode["archetype"], "coding-executor")
            self.assertIn("inbox", opencode)

    def test_build_store_config_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = build_store_config(data_dir=tmp, mail_root=MAILBUS_ROOT)
            errors = validate_config(cfg)
            self.assertEqual(errors, [], msg=str(errors))
            self.assertGreaterEqual(len(cfg["agents"]), 1)
            self.assertIn("mailbus_internal_llm", cfg)
            po = cfg.get("pipeline_ops") or {}
            self.assertIn("role_failover", po)

    def test_run_init_store_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = run_init_store(tmp, fresh=True, mail_root=MAILBUS_ROOT, quiet=True)
            self.assertEqual(rc, 0)
            config_path = os.path.join(tmp, "config.json")
            self.assertTrue(os.path.isfile(config_path))
            cfg = json.load(open(config_path, encoding="utf-8"))
            self.assertGreaterEqual(len(cfg["agents"]), 1)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "roles", "json", "role-flow.json")))
            self.assertTrue(os.path.isfile(os.path.join(tmp, "rules", "common", "task-fsm.md")))
            self.assertTrue(os.path.isdir(os.path.join(tmp, "work-orders")))
            self.assertTrue(os.path.isfile(os.path.join(tmp, "human-queue.json")))
            for sub in ("inbox", "msg-results", "agentmemory-pending", "locks"):
                self.assertTrue(os.path.isdir(os.path.join(tmp, sub)), msg=sub)

    def test_run_merge_store_config_updates_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = run_init_store(tmp, fresh=True, mail_root=MAILBUS_ROOT, quiet=True)
            self.assertEqual(rc, 0)
            config_path = os.path.join(tmp, "config.json")
            cfg = json.load(open(config_path, encoding="utf-8"))
            claude = next((a for a in cfg["agents"] if cfg["agents"][a].get("type") == "claude_code"), None)
            if claude is None:
                self.skipTest("no claude_code agent in fresh store")
            cfg["agents"][claude]["claude"] = {}
            json.dump(cfg, open(config_path, "w", encoding="utf-8"))
            rc = run_merge_store_config(tmp, mail_root=MAILBUS_ROOT, quiet=True)
            self.assertEqual(rc, 0)
            merged = json.load(open(config_path, encoding="utf-8"))
            launch = merged["agents"][claude].get("launch") or {}
            self.assertEqual(launch.get("template"), "claude_host")

    def test_mirror_org_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied = mirror_org_json(tmp, mail_root=MAILBUS_ROOT)
            self.assertIn("role-flow.json", copied)
            self.assertIn("roster.json", copied)


if __name__ == "__main__":
    unittest.main()
