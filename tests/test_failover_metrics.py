"""Failover metrics + doctor sundown/asset conflict."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.adapters.ops.doctor_checks import (
    check_asset_path_env_conflict,
    check_mail_path_alias_sunset,
)
from lib.application.orchestration.dispatch.failover_metrics import collect_failover_metrics
from lib.infra.utils import json_write


class TestFailoverMetrics(unittest.TestCase):
    def test_collects_dispatch_meta(self):
        with tempfile.TemporaryDirectory() as td:
            tasks = Path(td) / "tasks"
            tasks.mkdir()
            json_write(
                str(tasks / "t1.json"),
                {
                    "task_id": "t1",
                    "updated_at": "2026-09-13T00:00:00Z",
                    "chain": [
                        {
                            "step_id": "s1",
                            "to_agent": "agent-g",
                            "failover_tried": ["agent-e"],
                            "dispatch_meta": {
                                "method": "pipeline_role_failover",
                                "failover_from": "agent-e",
                                "failover_at": "2026-09-13T00:00:00Z",
                                "failover_tier": "similar_role",
                                "reason": "test_push",
                            },
                        }
                    ],
                },
            )
            m = collect_failover_metrics(td)
            self.assertEqual(m["event_count"], 1)
            self.assertEqual(m["by_from_agent"].get("agent-e"), 1)
            self.assertEqual(m["by_tier"].get("similar_role"), 1)


class TestMailSunsetAndAssetConflict(unittest.TestCase):
    def test_mail_prefix_warn(self):
        items = check_mail_path_alias_sunset(
            {"skills": [{"path": "mail/skills/common/x"}]}
        )
        self.assertTrue(any(i.level == "warn" and "mail/" in i.message for i in items))

    def test_mailbus_ok(self):
        items = check_mail_path_alias_sunset(
            {"skills": [{"path": "mailbus/skills/common/x"}]}
        )
        self.assertTrue(any(i.level == "ok" for i in items))
        self.assertFalse(any(i.level == "warn" and "mail/" in i.message for i in items))

    def test_asset_env_conflict(self):
        with patch.dict(os.environ, {"MAILBUS_SKILLS_ROOT": "D:/other/skills"}, clear=False):
            items = check_asset_path_env_conflict(
                {
                    "asset_paths": {
                        "skills": {"mode": "custom", "path": "E:/vault/skills"},
                    }
                }
            )
        self.assertTrue(any(i.level == "warn" and "双源" in i.message for i in items))


if __name__ == "__main__":
    unittest.main()
