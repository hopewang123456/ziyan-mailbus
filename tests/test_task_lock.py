"""Task lock 命名空间测试。"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.task_lock import (
    acquire_task_lock,
    read_task_lock,
    release_task_lock,
    task_lock_holder,
    task_lock_path,
)


class TestTaskLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "locks"), exist_ok=True)
        self.tid = "lock-test-task"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_acquire_and_release(self):
        self.assertTrue(acquire_task_lock(self.tmp, self.tid, "agent-a"))
        self.assertEqual(task_lock_holder(self.tmp, self.tid), "agent-a")
        lock = read_task_lock(self.tmp, self.tid)
        self.assertEqual(lock.get("holder"), "agent-a")
        self.assertTrue(os.path.isfile(task_lock_path(self.tmp, self.tid)))
        self.assertTrue(release_task_lock(self.tmp, self.tid, "agent-a"))
        self.assertIsNone(task_lock_holder(self.tmp, self.tid))

    def test_conflict_blocks_second_holder(self):
        self.assertTrue(acquire_task_lock(self.tmp, self.tid, "agent-a"))
        self.assertFalse(acquire_task_lock(self.tmp, self.tid, "agent-b"))
        self.assertTrue(release_task_lock(self.tmp, self.tid, "agent-a"))
        self.assertTrue(acquire_task_lock(self.tmp, self.tid, "agent-b"))

    def test_reentrant_same_holder(self):
        self.assertTrue(acquire_task_lock(self.tmp, self.tid, "scan"))
        self.assertTrue(acquire_task_lock(self.tmp, self.tid, "scan"))


if __name__ == "__main__":
    unittest.main()
