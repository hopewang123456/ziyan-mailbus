import os
import unittest

from lib.utils import to_container_store_path, rewrite_host_store_refs, CONTAINER_STORE_MARKERS


class TestContainerPaths(unittest.TestCase):
    def test_markers_include_phase3_paths(self):
        for marker in (
            "work-orders/",
            "deliverables/",
            "human-queue",
            "agentmemory-pending/",
        ):
            self.assertIn(marker, CONTAINER_STORE_MARKERS)

    def test_to_container_store_path_windows(self):
        data = r"E:\ai_tools\mail\store"
        p = os.path.join(data, "msg-files", "msg-1.md")
        self.assertEqual(
            to_container_store_path(data, p),
            "/mailbus/store/msg-files/msg-1.md",
        )

    def test_to_container_work_orders(self):
        data = r"E:\ai_tools\mail\store"
        p = os.path.join(data, "work-orders", "task-1", "step-2.md")
        self.assertEqual(
            to_container_store_path(data, p),
            "/mailbus/store/work-orders/task-1/step-2.md",
        )

    def test_to_container_deliverables(self):
        data = r"E:\ai_tools\mail\store"
        p = os.path.join(data, "deliverables", "game-1", "README.md")
        self.assertEqual(
            to_container_store_path(data, p),
            "/mailbus/store/deliverables/game-1/README.md",
        )

    def test_to_container_human_queue(self):
        data = r"E:\ai_tools\mail\store"
        p = os.path.join(data, "human-queue.json")
        self.assertEqual(
            to_container_store_path(data, p),
            "/mailbus/store/human-queue.json",
        )

    def test_to_container_agentmemory_pending(self):
        data = r"E:\ai_tools\mail\store"
        p = os.path.join(data, "agentmemory-pending", "item-1.json")
        self.assertEqual(
            to_container_store_path(data, p),
            "/mailbus/store/agentmemory-pending/item-1.json",
        )

    def test_rewrite_host_store_refs(self):
        data = r"E:\ai_tools\mail\store"
        text = f"任务文件: {data}\\msg-files\\x.md"
        out = rewrite_host_store_refs(
            data, text, {"type": "hermes_profile"},
        )
        self.assertIn("/mailbus/store/msg-files/x.md", out)
        self.assertNotIn("E:\\", out)


if __name__ == "__main__":
    unittest.main()
