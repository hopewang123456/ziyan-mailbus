"""M1 W3 宿主哨兵测试：新增告警/节流/恢复/每日摘要。"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import mailbus_sentinel as sentinel


def _tmp():
    return tempfile.mkdtemp(prefix="mb-sentinel-")


def _report(warns):
    items = {k: {"status": "warn" if k in warns else "ok", "detail": f"{k}-detail"} for k in
             ("serve_api", "scheduler", "patrol", "daily", "ledger", "human_queue")}
    return {"ok": not warns, "checked_at": "2026-09-28 12:00:00", "items": items}


class TestSentinel(unittest.TestCase):
    def _run(self, tmp, warns, **kw):
        # 哨兵内部取真实 now——过午（>=12 点）会触发 digest 干扰动作断言，
        # 与 wave1 午夜定时炸弹同类：一律钉在上午
        from lib.infra.clock import now_dt
        fake_now = now_dt().replace(hour=9, minute=0, second=0, microsecond=0)
        sent = []
        with patch.object(sentinel, "acceptance_status", return_value=_report(warns)), \
             patch.object(sentinel, "send_notification",
                          side_effect=lambda d, t, b, level="warn": sent.append((level, t))), \
             patch("lib.infra.clock.now_dt", return_value=fake_now):
            try:
                r = sentinel.run_sentinel(tmp, **kw)
            finally:
                self._sent = sent
        return r, self._sent

    def setUp(self):
        self._sent = []

    def test_new_warn_alerts_once_then_throttles(self):
        tmp = _tmp()
        r, sent = self._run(tmp, {"scheduler"})
        self.assertIn("alert:new_warn", r["actions"])
        self.assertEqual(len(sent), 1)

        # 相同 warn：节流（24h 内不再呼）
        self._sent = []
        r2, sent2 = self._run(tmp, {"scheduler"})
        self.assertEqual(sent2, [])
        self.assertEqual(r2["actions"], [])  # 12 点前的 _report 也不触发 digest

    def test_remind_after_window(self):
        tmp = _tmp()
        self._run(tmp, {"scheduler"})
        # last_alert_at 拨回 25h 前——以 _run 钉死的「今天 09:00」为基准（同一时钟）
        import json
        state_path = os.path.join(tmp, sentinel.STATE_FILE)
        state = json.load(open(state_path, encoding="utf-8"))
        from datetime import timedelta
        from lib.infra.clock import now_dt
        pinned = now_dt().replace(hour=9, minute=0, second=0, microsecond=0)
        state["last_alert_at"] = (pinned - timedelta(hours=25)).isoformat()
        json.dump(state, open(state_path, "w", encoding="utf-8"))
        self._sent = []
        r, sent = self._run(tmp, {"scheduler"})
        self.assertIn("alert:remind", r["actions"])
        self.assertEqual(len(sent), 1)

    def test_recovery_alerts(self):
        tmp = _tmp()
        self._run(tmp, {"serve_api"})
        self._sent = []
        r, sent = self._run(tmp, set())
        self.assertIn("alert:recovered", r["actions"])
        self.assertEqual(len(sent), 1)
        # 一直健康不再呼
        self._sent = []
        r2, sent2 = self._run(tmp, set())
        self.assertEqual(sent2, [])

    def test_daily_digest_once_after_noon(self):
        # checked_at 12:00（_report 固定），run_sentinel 内部取真实 now——
        # 用 patch 固定 now 在 12 点后
        from lib.infra.clock import now_dt
        fake_now = now_dt().replace(hour=12, minute=5, second=0, microsecond=0)
        tmp = _tmp()
        with patch.object(sentinel, "acceptance_status", return_value=_report(set())), \
             patch.object(sentinel, "send_notification",
                          side_effect=lambda d, t, b, level="warn": self._sent.append(level)), \
             patch("lib.infra.clock.now_dt", return_value=fake_now):
            r1 = sentinel.run_sentinel(tmp)
            r2 = sentinel.run_sentinel(tmp)
        self.assertIn("digest", r1["actions"])
        self.assertNotIn("digest", r2["actions"])  # 同日只发一次
        self.assertEqual(self._sent, ["digest"])


if __name__ == "__main__":
    unittest.main()
