"""M1 W2 告警外呼接线测试：alerter / scheduler 连败 / human-queue 异常条目 / 日报摘要。"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _tmp():
    return tempfile.mkdtemp(prefix="mb-wiring-")


class TestAlerterWiring(unittest.TestCase):
    def _push(self, tmp, severity):
        from lib.adapters.ops.alerter import push_alert
        push_alert(tmp, "agent_offline", severity, "agent-x", "agent-x offline")

    def test_critical_and_warn_notify_info_does_not(self):
        from lib.adapters.ops.alerter import push_alert

        sent = []
        with patch("lib.adapters.ops.notifier.send_notification",
                   side_effect=lambda d, t, b, level="warn": sent.append((level, t))):
            tmp = _tmp()
            push_alert(tmp, "agent_offline", "critical", "agent-x", "agent-x offline")
            push_alert(tmp, "agentmemory_down", "warn", "agent-x", "am down")  # 不同 type 避开 dedupe
            push_alert(tmp, "api_unreachable", "info", "agent-x", "api slow")
        self.assertEqual([s[0] for s in sent], ["critical", "warn"])

    def test_dedupe_does_not_renotify(self):
        sent = []
        with patch("lib.adapters.ops.notifier.send_notification",
                   side_effect=lambda d, t, b, level="warn": sent.append(t)):
            tmp = _tmp()
            self._push(tmp, "critical")
            self._push(tmp, "critical")  # 同 type+agent active 告警 → dedupe return
        self.assertEqual(len(sent), 1)


class TestSchedulerFailStreak(unittest.TestCase):
    def test_streak_alerts_once_at_threshold(self):
        from lib.adapters.ops.scheduler import _alert_job_fail_streak

        sent = []
        with patch("lib.adapters.ops.notifier.send_notification",
                   side_effect=lambda d, t, b, level="warn": sent.append(t)):
            st = {}
            tmp = _tmp()
            for _ in range(2):
                _alert_job_fail_streak(tmp, "scan", st, "boom\nFatal: x")
            self.assertEqual(sent, [])
            self.assertEqual(st["fail_streak"], 2)
            _alert_job_fail_streak(tmp, "scan", st, "boom\nFatal: x")
            self.assertEqual(len(sent), 1)   # 阈值 3 呼一次
            _alert_job_fail_streak(tmp, "scan", st, "boom")
            self.assertEqual(len(sent), 1)   # 之后不再重复
        self.assertEqual(st["fail_streak"], 4)

    def test_threshold_from_config(self):
        from lib.adapters.ops.scheduler import _alert_job_fail_streak
        import json

        tmp = _tmp()
        with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as fh:
            json.dump({"notify": {"job_fail_alert_after": 2}}, fh)
        sent = []
        with patch("lib.adapters.ops.notifier.send_notification",
                   side_effect=lambda d, t, b, level="warn": sent.append(t)):
            st = {}
            _alert_job_fail_streak(tmp, "scan", st, "x")
            self.assertEqual(sent, [])
            _alert_job_fail_streak(tmp, "scan", st, "x")
            self.assertEqual(len(sent), 1)


class TestHumanQueueWiring(unittest.TestCase):
    def test_abnormal_source_notifies(self):
        from lib.adapters.orchestration.human_queue import enqueue

        sent = []
        with patch("lib.adapters.ops.notifier.send_notification",
                   side_effect=lambda d, t, b, level="warn": sent.append(t)):
            tmp = _tmp()
            enqueue(tmp, {"type": "workflow_gate", "task_id": "t1", "source": "station_vacancy",
                          "title": "工位空缺", "reason": "dev 工位全空缺"})
            enqueue(tmp, {"type": "final_acceptance", "task_id": "t2"})
        self.assertEqual(len(sent), 1)
        self.assertIn("station_vacancy", sent[0])


class TestDailyDigestWiring(unittest.TestCase):
    def test_daily_report_sends_digest(self):
        from lib.adapters.ops.jobs import run_daily_report

        sent = []
        with patch("lib.adapters.ops.jobs.fleet_health_lines", return_value=["- 18 agents ok"]), \
             patch("lib.adapters.ops.jobs._patrol_target", return_value="lingxun"), \
             patch("lib.adapters.ops.jobs._write_report_file", return_value="/tmp/x.md"), \
             patch("lib.adapters.ops.jobs._append_inbox_notice"), \
             patch("lib.adapters.ops.notifier.send_notification",
                   side_effect=lambda d, t, b, level="warn": sent.append(level)):
            rc = run_daily_report(_tmp())
        self.assertEqual(rc, 0)
        self.assertEqual(sent, ["digest"])


class TestDailyBackfill(unittest.TestCase):
    """10-04/10-05 日报缺失回归：cron 错过（宿主睡眠）时 patrol 补账。"""

    def _setup(self, tmp):
        import os

        daily = os.path.join(tmp, "reports", "daily")
        os.makedirs(daily, exist_ok=True)
        return daily

    def _run_ensure(self, tmp, hour, minute):
        from unittest.mock import patch

        from lib.adapters.ops import jobs

        fake_now = None
        from lib.infra.clock import now_dt

        base = now_dt().replace(hour=hour, minute=minute, second=0, microsecond=0)
        with patch("lib.adapters.ops.jobs.now_dt", return_value=base), \
             patch("lib.adapters.ops.jobs.run_daily_report") as mrun, \
             patch("lib.adapters.ops.jobs._now_iso", return_value="x"):
            r = jobs.ensure_daily_report(tmp)
        return r, mrun

    def test_backfills_when_missing_after_grace(self):
        from lib.adapters.ops.jobs import ensure_daily_report
        import os

        tmp = _tmp()
        daily = self._setup(tmp)
        r, mrun = self._run_ensure(tmp, 14, 0)
        self.assertTrue(r)
        mrun.assert_called_once()
        # run_daily_report 真跑会写当日文件（这里被 mock，验证判定逻辑即可）

    def test_skips_when_report_exists(self):
        from lib.adapters.ops.jobs import ensure_daily_report
        from datetime import timedelta
        from lib.infra.clock import now_dt
        import os

        tmp = _tmp()
        daily = self._setup(tmp)
        today = now_dt().strftime("%Y-%m-%d")
        with open(os.path.join(daily, f"{today}.md"), "w", encoding="utf-8") as fh:
            fh.write("x")
        r, mrun = self._run_ensure(tmp, 14, 0)
        self.assertFalse(r)
        mrun.assert_not_called()

    def test_skips_before_cron_window(self):
        from lib.adapters.ops.jobs import ensure_daily_report

        tmp = _tmp()
        self._setup(tmp)
        r, mrun = self._run_ensure(tmp, 9, 0)
        self.assertFalse(r)
        mrun.assert_not_called()


if __name__ == "__main__":
    unittest.main()
