"""Wave-1 workflow slices: fleet health report, audit reviewer fallback, task templates."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestFleetHealthLines(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = self.tmp.name
        os.makedirs(os.path.join(self.data_dir, "inbox", "alpha"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "errors"), exist_ok=True)
        with open(os.path.join(self.data_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"agents": {"alpha": {"type": "none"}}}, f)
        with open(os.path.join(self.data_dir, "inbox", "alpha", "inbox.json"), "w", encoding="utf-8") as f:
            json.dump({"agent": "alpha", "messages": [
                {"id": "m1", "status": "pending"},
                {"id": "m2", "status": "pushed"},
                {"id": "m3", "status": "done"},
                {"id": "m4", "status": "acknowledged"},
            ]}, f)

    def tearDown(self):
        self.tmp.cleanup()

    def test_backlog_counts_unfinished_only(self):
        from lib.adapters.ops.jobs import fleet_health_lines
        lines = fleet_health_lines(self.data_dir)
        joined = "\n".join(lines)
        self.assertIn("alpha:2", joined)   # pending + pushed
        self.assertIn("agents: 1", joined)

    def test_recent_errors_counted(self):
        from datetime import datetime, timedelta, timezone

        from lib.adapters.ops.jobs import fleet_health_lines
        # ts 相对 now：硬编码日期会在跨午夜时滑出 24h 窗口（time-bomb）
        recent = datetime.now(timezone(timedelta(hours=8))) - timedelta(hours=1)
        with open(os.path.join(self.data_dir, "errors", "e.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "x", "ts": recent.strftime("%Y-%m-%dT%H:%M:%S+0800")}) + "\n")
            f.write(json.dumps({"event": "old", "ts": "2025-01-01T00:00:00+0800"}) + "\n")
        lines = fleet_health_lines(self.data_dir)
        self.assertIn("近 24h 错误记录: 1", "\n".join(lines))


class TestAuditReviewerFallback(unittest.TestCase):
    def test_missing_demo_reviewer_falls_back_to_roster(self):
        from lib.application.orchestration.tracker import _resolve_audit_reviewer
        agents = {"exec": {"type": "none"}, "other": {"type": "none"}}
        req, reviewer = _resolve_audit_reviewer("", agents, first_agent="exec")
        self.assertTrue(req)
        self.assertEqual(reviewer, "other")  # 避开首步执行者

    def test_no_usable_reviewer_disables_audit(self):
        from lib.application.orchestration.tracker import _resolve_audit_reviewer
        req, reviewer = _resolve_audit_reviewer("", {}, first_agent="")
        self.assertFalse(req)
        self.assertEqual(reviewer, "")


class TestTaskTemplates(unittest.TestCase):
    def test_templates_valid_role_types(self):
        from lib.infra.constants import MAILBUS_ROOT
        from lib.adapters.locale.role_labels import valid_role_types
        path = os.path.join(str(MAILBUS_ROOT), "config", "mailbus", "task-templates.json")
        with open(path, encoding="utf-8") as f:
            tpls = json.load(f).get("templates") or []
        self.assertTrue({t["id"] for t in tpls} >= {"single-step", "two-step-review", "patrol-check"})
        valid = set(valid_role_types(""))
        for t in tpls:
            chain = (t.get("envelope") or {}).get("planned_chain") or []
            self.assertTrue(chain, t["id"])
            for st in chain:
                self.assertIn(st["role_type"], valid, f"{t['id']} role_type {st['role_type']}")


if __name__ == "__main__":
    unittest.main()
