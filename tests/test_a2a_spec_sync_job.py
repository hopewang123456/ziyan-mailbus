"""a2a-spec-sync scheduler job 烟雾测试。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.infra.constants import MAILBUS_ROOT
from lib.adapters.ops.jobs import run_a2a_spec_sync
from lib.adapters.ops.scheduler import DEFAULT_JOBS, _register_runners, _JOB_RUNNERS


class TestA2aSpecSyncJob(unittest.TestCase):
    def test_jobs_json_has_a2a_spec_sync(self):
        path = MAILBUS_ROOT / "config" / "scheduler" / "jobs.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        jobs = {j["id"]: j for j in data.get("jobs") or []}
        self.assertIn("a2a-spec-sync", jobs)
        job = jobs["a2a-spec-sync"]
        self.assertTrue(job.get("enabled"))
        self.assertEqual(job.get("interval_seconds"), 604800)
        self.assertEqual(job.get("lock"), "mailbus-a2a-spec-sync")

    def test_default_jobs_and_runner_registered(self):
        ids = {j["id"] for j in DEFAULT_JOBS}
        self.assertIn("a2a-spec-sync", ids)
        _register_runners()
        self.assertIn("a2a-spec-sync", _JOB_RUNNERS)

    def test_run_a2a_spec_sync_updates_tracker(self):
        # data_dir 须为 mail 根下子目录，_mail_root 才能定位 tools/
        with tempfile.TemporaryDirectory(dir=str(MAILBUS_ROOT)) as td:
            rc = run_a2a_spec_sync(td)
            self.assertEqual(rc, 0)
            target = os.path.join(td, "config", "a2a-protocol.json")
            self.assertTrue(os.path.isfile(target), target)
            doc = json.loads(open(target, encoding="utf-8").read())
            self.assertEqual(doc.get("last_sync_source"), "a2a-sync-spec.py")
            self.assertIn("wire_version_latest_release", doc)


if __name__ == "__main__":
    unittest.main()
