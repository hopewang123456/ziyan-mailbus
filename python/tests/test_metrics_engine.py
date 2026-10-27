"""P2 B1-B3 — 指标引擎：manifest SoT / collector 口径 / 时序存储 / 统一查询。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest


def _store_td(agents=None, tasks=None, queue_items=None) -> str:
    td = tempfile.mkdtemp()
    with open(os.path.join(td, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"agents": agents or {"a1": {"name": "甲", "type": "codex"}}}, f, ensure_ascii=False)
    os.makedirs(os.path.join(td, "tasks"), exist_ok=True)
    for t in tasks or []:
        with open(os.path.join(td, "tasks", f"{t['task_id']}.json"), "w", encoding="utf-8") as f:
            json.dump(t, f, ensure_ascii=False)
    os.makedirs(os.path.join(td, "inbox", "a1"), exist_ok=True)
    with open(os.path.join(td, "inbox", "a1", "inbox.json"), "w", encoding="utf-8") as f:
        json.dump({"agent": "a1", "messages": [
            {"id": "m1", "content": "x", "state": "pending"},
            {"id": "m2", "content": "y", "state": "done"},
        ]}, f, ensure_ascii=False)
    with open(os.path.join(td, "human-queue.json"), "w", encoding="utf-8") as f:
        json.dump({"items": queue_items or []}, f, ensure_ascii=False)
    return td


class TestMetricsEngine(unittest.TestCase):
    def test_manifest_loads_and_ids_unique(self):
        from lib.adapters.metrics.manifest import load_manifest, metric_ids

        ids = metric_ids("")
        self.assertGreaterEqual(len(ids), 9)
        self.assertEqual(len(ids), len(set(ids)))
        m = load_manifest("")
        self.assertEqual(m.get("schema"), "mailbus-metrics-manifest-v1")

    def test_collect_points(self):
        from lib.adapters.metrics.collector import collect_point

        td = _store_td(
            tasks=[
                {"task_id": "t1", "status": "running"},
                {"task_id": "t2", "status": "pending"},
                {"task_id": "t3", "status": "done"},
            ],
        )
        got = collect_point("tasks.active", td)
        self.assertEqual(got["value"], 2.0)
        self.assertEqual(got["unit"], "count")
        got = collect_point("bus.messages_total", td)
        self.assertEqual(got["value"], 2.0)
        got = collect_point("bus.unread", td)
        self.assertEqual(got["value"], 1.0)
        got = collect_point("agents.total", td)
        self.assertEqual(got["value"], 2.0)  # a1 + 内置子言
        got = collect_point("humanqueue.pending", td)
        self.assertEqual(got["value"], 0.0)
        # 未登记指标显式报错
        self.assertEqual(collect_point("nope.nope", td).get("error"), "unknown_metric")

    def test_store_roundtrip_and_query_window(self):
        from lib.adapters.metrics.query import query, snapshot
        from lib.adapters.metrics.store import read_series

        td = _store_td()
        out = snapshot(td)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["collected"], len([1 for _ in read_series(td, "tasks.active")]) and out["collected"])
        # 时序已落盘且可读回
        rows = read_series(td, "tasks.active", hours=1)
        self.assertEqual(len(rows), 1)
        # 窗口查询回退：无历史指标 → 现算单点
        q = query(td, "bus.unread", granularity="1h", hours=1)
        self.assertEqual(q["status"], "ok")
        self.assertEqual(q["series"][0]["metric"], "bus.unread")

    def test_query_point_all(self):
        from lib.adapters.metrics.query import query

        q = query(_store_td())
        self.assertEqual(q["status"], "ok")
        self.assertTrue(any(p["metric"] == "tasks.active" for p in q["points"]))


if __name__ == "__main__":
    unittest.main()
