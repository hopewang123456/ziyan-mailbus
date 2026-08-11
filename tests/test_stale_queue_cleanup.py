"""scanner: stale queue 清理。"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.domain.models import MsgStatus
from lib.application.scan import _cleanup_stale_queue_files
from lib.infra.utils import json_write


class TestStaleQueueCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for sub in ("inbox/lingzhao", "queue/urgent", "queue/normal"):
            os.makedirs(os.path.join(self.tmp, sub), exist_ok=True)
        json_write(
            os.path.join(self.tmp, "inbox", "lingzhao", "inbox.json"),
            {"agent": "lingzhao", "has_unread": False, "messages": [], "since": "2026-06-17T00:00:00+0800"},
        )
        json_write(
            os.path.join(self.tmp, "queue", "urgent", "lingzhao.json"),
            [{"id": "msg-stale", "state": "pending"}],
        )

    def test_removes_stale_queue_when_no_pending_inbox(self):
        n = _cleanup_stale_queue_files(self.tmp, {"lingzhao": {}})
        self.assertEqual(n, 1)
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, "queue", "urgent", "lingzhao.json")))


if __name__ == "__main__":
    unittest.main()
