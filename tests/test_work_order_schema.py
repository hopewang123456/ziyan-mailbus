"""Work order schema 与路径双轨测试。"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.pipeline_work_order import (
    legacy_msg_file_path,
    parse_work_order_status,
    resolve_work_order_path,
    validate_work_order_schema,
    work_order_path,
    write_pipeline_work_order,
)


class TestWorkOrderSchema(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_creates_work_orders_and_legacy(self):
        mid, wo = write_pipeline_work_order(
            self.tmp,
            task_id="game-courier",
            step_num=1,
            to_person="dali",
            to_role="编码执行",
            summary="实现 courier 模块",
            step_id="s1",
        )
        self.assertTrue(os.path.isfile(wo))
        self.assertEqual(wo, work_order_path(self.tmp, "game-courier", "s1"))
        legacy = legacy_msg_file_path(self.tmp, mid)
        self.assertTrue(os.path.isfile(legacy))
        with open(wo, encoding="utf-8") as f:
            content = f.read()
        ok, errs = validate_work_order_schema(content)
        self.assertTrue(ok, errs)
        self.assertEqual(parse_work_order_status(content), "in_progress")
        self.assertIn("Intent", content)
        self.assertIn("game-courier", content)

    def test_resolve_prefers_work_orders(self):
        write_pipeline_work_order(
            self.tmp,
            task_id="t1",
            step_num=2,
            to_person="lingxiao",
            to_role="开发",
            step_id="s2",
        )
        resolved = resolve_work_order_path(
            self.tmp, task_id="t1", step_id="s2", msg_id="msg-x",
        )
        self.assertEqual(resolved, work_order_path(self.tmp, "t1", "s2"))

    def test_resolve_fallback_msg_files(self):
        os.makedirs(os.path.join(self.tmp, "msg-files"), exist_ok=True)
        legacy = legacy_msg_file_path(self.tmp, "msg-only")
        with open(legacy, "w", encoding="utf-8") as f:
            f.write("# legacy\n\ntask_id | t9\nstep_id | s1\nmsg-results path\n")
        resolved = resolve_work_order_path(self.tmp, msg_id="msg-only")
        self.assertEqual(resolved, legacy)


if __name__ == "__main__":
    unittest.main()
