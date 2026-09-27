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


if __name__ == "__main__":
    unittest.main()
