"""Wave4 integrations + Wave5 smoke."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lib.adapters.integrations.plugin_registry import list_integrations, register_integration
from lib.application.integrations_query import integrations_overview
from lib.application.ops.repair_pipeline import report_stuck_pipeline
from lib.application.ops.store_cleanup import (
    archive_inbox_backlog,
    list_store_agents,
    prune_agent_queues,
)
from lib.application.ops.pipeline_watchdog import running_pipeline_summary
from lib.application.ops.platform_scout import load_leads_sources, run_scout
from lib.composition import build_orchestration, get_context
from lib.ports import AuditPort, HumanGatePort



class TestPluginRegistry(unittest.TestCase):
    def test_builtins_listed(self):
        names = {i["name"] for i in list_integrations()}
        self.assertIn("gpu", names)
        self.assertIn("n8n", names)
        self.assertIn("comfyui", names)
        self.assertIn("external_tools", names)

    def test_register_extra(self):
        register_integration("demo_w4", lambda: "ok", kind="test", description="demo")
        names = {i["name"] for i in list_integrations()}
        self.assertIn("demo_w4", names)


class TestIntegrationsQuery(unittest.TestCase):
    def test_overview(self):
        out = integrations_overview("/tmp")
        self.assertTrue(out["ok"])
        self.assertGreaterEqual(out["count"], 4)


class TestRepairOps(unittest.TestCase):
    def test_report_empty_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "tasks").mkdir()
            Path(tmp, "config.json").write_text("{}", encoding="utf-8")
            r = report_stuck_pipeline(tmp, "missing-task")
            self.assertEqual(r["task_id"], "missing-task")
            self.assertFalse(r["has_msg_results"])


class TestStoreCleanupOps(unittest.TestCase):
    def test_list_and_dry_run_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox" / "demo"
            inbox.mkdir(parents=True)
            (inbox / "inbox.json").write_text(
                '{"agent":"demo","has_unread":false,"messages":[],"since":"2026-01-01T00:00:00Z"}',
                encoding="utf-8",
            )
            Path(tmp, "archive").mkdir(exist_ok=True)
            Path(tmp, "queue", "urgent").mkdir(parents=True)
            Path(tmp, "queue", "normal").mkdir(parents=True)
            self.assertEqual(list_store_agents(tmp), ["demo"])
            out = archive_inbox_backlog(tmp, "demo", dry_run=True)
            self.assertEqual(out["would_archive"], 0)
            q = prune_agent_queues(tmp, "demo", dry_run=True)
            self.assertEqual(q["pruned"], 0)


class TestWatchdogOps(unittest.TestCase):
    def test_running_summary_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "tasks").mkdir()
            Path(tmp, "config.json").write_text("{}", encoding="utf-8")
            self.assertEqual(running_pipeline_summary(tmp), [])


class TestPlatformScoutOps(unittest.TestCase):
    def test_run_scout_no_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "config").mkdir()
            stats = run_scout(tmp, dry_run=True)
            self.assertEqual(stats["total"], 0)
            self.assertEqual(load_leads_sources(tmp), {})


class TestReservedPortsWired(unittest.TestCase):
    def test_orchestration_bundle_ports(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "system").mkdir()
            bundle = build_orchestration(tmp)
            self.assertIsInstance(bundle.human_gate, HumanGatePort)
            self.assertIsInstance(bundle.audit, AuditPort)
            bundle.audit.append("test_event", {"ok": True})
            ctx = get_context()
            self.assertTrue(hasattr(ctx.clock, "now_ts"))
            self.assertGreater(ctx.clock.now_ts(), 0)


class TestAlignSmoke(unittest.TestCase):
    def test_align_import_and_run(self):
        from lib.application.align_store import align_store_from_registry

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "config.json").write_text('{"agents": {}}', encoding="utf-8")
            out = align_store_from_registry(tmp, expect_min=0)
            self.assertIn("ok", out)


class TestGpuImport(unittest.TestCase):
    def test_gpu_module(self):
        from lib.adapters.integrations.gpu import load_gpu_sharing_config

        self.assertTrue(callable(load_gpu_sharing_config))


if __name__ == "__main__":
    unittest.main()
