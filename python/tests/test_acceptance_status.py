"""M1 W4 验收对账测试（acceptance status 六项检查）。"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.ops import acceptance
from lib.interfaces.clock import TZ_CST


def _tmp():
    return tempfile.mkdtemp(prefix="mb-acc-")


def _touch(path, content="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


class TestItems(unittest.TestCase):
    def test_patrol_fresh_ok_and_stale_warn(self):
        from datetime import timedelta
        from lib.infra.clock import now_dt

        now = now_dt()
        tmp = _tmp()
        fresh = now - timedelta(hours=1)
        _touch(os.path.join(tmp, "reports", "patrol", fresh.strftime("%Y%m%d-%H%M%S") + ".md"))
        r = acceptance._patrol_status(tmp, now)
        self.assertEqual(r["status"], "ok")

        stale = now - timedelta(days=2)
        tmp2 = _tmp()
        _touch(os.path.join(tmp2, "reports", "patrol", stale.strftime("%Y%m%d-%H%M%S") + ".md"))
        r2 = acceptance._patrol_status(tmp2, now)
        self.assertEqual(r2["status"], "warn")

    def test_daily_missing_counts(self):
        from datetime import timedelta
        from lib.infra.clock import now_dt

        # 固定到 13:00（11:35 之后）：当天也计入应产出，missing 数不受运行时刻影响
        now = now_dt().replace(hour=13, minute=0, second=0, microsecond=0)
        tmp = _tmp()
        # 只补昨天与前天 → 7 天缺 5 天（今天 + 4 个更早天）→ warn
        for d in (1, 2):
            day = (now - timedelta(days=d)).strftime("%Y-%m-%d")
            _touch(os.path.join(tmp, "reports", "daily", f"{day}.md"))
        r = acceptance._daily_status(tmp, now)
        self.assertEqual(r["status"], "warn")
        self.assertEqual(len(r["missing"]), 5)

    def test_queue_excludes_adjudicated(self):
        # 09-28 教训：approved/denied 不得计入 open
        from datetime import timedelta
        from lib.infra.clock import now_dt

        now = now_dt()
        old = (now - timedelta(hours=200)).strftime("%Y-%m-%dT%H:%M:%S")
        tmp = _tmp()
        with open(os.path.join(tmp, "human-queue.json"), "w", encoding="utf-8") as fh:
            json.dump({"items": [
                {"id": "a", "status": "approved", "created_at": old},
                {"id": "b", "status": "pending", "created_at": old},
            ]}, fh)
        r = acceptance._queue_status(tmp, now)
        self.assertEqual(r["open"], 1)
        self.assertEqual(r["status"], "warn")  # oldest 200h > 48h

    def test_scheduler_parses_tail(self):
        tmp = _tmp()
        from lib.infra.clock import now_dt
        now = now_dt()
        ts = now.strftime("%Y-%m-%dT%H:%M:%S")
        with open(os.path.join(tmp, "cron.log"), "a", encoding="utf-8") as fh:
            fh.write(f"\n[{ts}+0800] scheduler job=scan done rc=0 elapsed=1s\n")
        r = acceptance._scheduler_status(tmp, now)
        self.assertEqual(r["status"], "ok")
        self.assertLess(r["age_minutes"], 2)


class TestTimezoneRegression(unittest.TestCase):
    def test_local_tz_is_cst_not_env_dependent(self):
        # 回归：load_mailbus_env 设 TZ 后 Windows astimezone 会变 UTC，
        # 曾导致全部年龄偏 -8h
        self.assertIs(acceptance._LOCAL_TZ, TZ_CST)

    def test_parse_ts_offset(self):
        t = acceptance._parse_ts("2026-09-28T00:41:00")
        self.assertEqual(t.utcoffset().total_seconds(), 8 * 3600)


class TestAggregate(unittest.TestCase):
    def test_aggregate_ok_and_json_serializable(self):
        with patch("lib.adapters.ops.acceptance._api_status", return_value={"status": "ok", "detail": "stub"}):
            r = acceptance.acceptance_status(_tmp(), api_base="http://127.0.0.1:1")
        self.assertIn("ok", r)
        self.assertEqual(len(r["items"]), 6)
        json.dumps(r)  # 哨兵消费 --json，必须可序列化


if __name__ == "__main__":
    unittest.main()
