"""M1 W1 外呼通知渠道测试（desktop/webhook/smtp/file + 分发隔离）。"""
import json
import os
import smtplib
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.ops import notifier


class _FakeResp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture_post():
    calls = []

    def fake_urlopen(req, timeout=10):
        calls.append({"url": req.full_url, "data": json.loads(req.data.decode("utf-8"))})
        return _FakeResp()

    return calls, fake_urlopen


def _write_config(tmp, notify):
    os.makedirs(tmp, exist_ok=True)
    with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as fh:
        json.dump({"notify": notify}, fh)
    return tmp


class TestDesktop(unittest.TestCase):
    def test_windows_balloon_popen(self):
        argv = []
        with patch("os.name", "nt"), \
             patch.dict(os.environ, {"OS": "Windows_NT"}, clear=False), \
             patch("lib.adapters.ops.notifier.shutil.which", return_value="powershell"), \
             patch("lib.adapters.ops.notifier.subprocess.Popen", side_effect=lambda a, **k: argv.append(a)):
            r = notifier._send_desktop("ti'tle", "bo\ndy")
        self.assertTrue(r["ok"])
        script = argv[0][3]
        self.assertIn("'ti''tle'", script)
        self.assertIn("bo dy", script)  # 换行被压平，防 PS 注入

    def test_linux_notify_send(self):
        with patch("os.name", "posix"), \
             patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True), \
             patch("lib.adapters.ops.notifier.shutil.which", return_value="/usr/bin/notify-send"), \
             patch("lib.adapters.ops.notifier.subprocess.run") as mrun:
            r = notifier._send_desktop("t", "b")
        self.assertTrue(r["ok"])
        mrun.assert_called_once()

    def test_linux_no_display_degrades(self):
        # clear=True 同时剔除 Windows 宿主的 OS=Windows_NT，强制走 posix 分支
        with patch("os.name", "posix"), patch.dict(os.environ, {}, clear=True):
            r = notifier._send_desktop("t", "b")
        self.assertFalse(r["ok"])
        self.assertIn("no desktop", r["error"])


class TestWebhook(unittest.TestCase):
    def test_generic_payload(self):
        calls, fake = _capture_post()
        with patch("lib.adapters.ops.notifier.urllib.request.urlopen", side_effect=fake):
            r = notifier._send_webhook({"url": "http://x/hook"}, "t1", "b1", "warn")
        self.assertTrue(r["ok"])
        self.assertEqual(calls[0]["data"]["title"], "t1")
        self.assertEqual(calls[0]["data"]["level"], "warn")

    def test_telegram_payload(self):
        calls, fake = _capture_post()
        cfg = {"provider": "telegram", "url": "https://api.telegram.org/bot123/sendMessage", "chat_id": "42"}
        with patch("lib.adapters.ops.notifier.urllib.request.urlopen", side_effect=fake):
            notifier._send_webhook(cfg, "t", "b", "critical")
        self.assertIn("42", calls[0]["data"]["chat_id"])
        self.assertIn("CRITICAL", calls[0]["data"]["text"])

    def test_dingtalk_signed(self):
        calls, fake = _capture_post()
        cfg = {"provider": "dingtalk", "url": "https://oapi.dingtalk.com/robot/send", "secret": "s3cr3t"}
        with patch("lib.adapters.ops.notifier.urllib.request.urlopen", side_effect=fake):
            r = notifier._send_webhook(cfg, "t", "b", "warn")
        self.assertTrue(r["ok"])
        self.assertIn("timestamp=", calls[0]["url"])
        self.assertIn("sign=", calls[0]["url"])
        self.assertEqual(calls[0]["data"]["msgtype"], "markdown")

    def test_missing_url(self):
        r = notifier._send_webhook({"provider": "generic"}, "t", "b", "warn")
        self.assertFalse(r["ok"])


class TestSmtp(unittest.TestCase):
    def test_ssl_send(self):
        client = MagicMock()
        with patch("lib.adapters.ops.notifier.smtplib.SMTP_SSL", return_value=client):
            r = notifier._send_smtp(
                {"host": "smtp.example.com", "port": 465, "username": "u", "password": "p",
                 "from": "a@x.com", "to": ["b@y.com"]},
                "标题", "内容",
            )
        self.assertTrue(r["ok"])
        client.login.assert_called_once()
        self.assertEqual(client.sendmail.call_count, 1)

    def test_missing_host(self):
        self.assertFalse(notifier._send_smtp({"to": ["b@y.com"]}, "t", "b")["ok"])


class TestFile(unittest.TestCase):
    def test_default_daily_digest_path(self):
        tmp = tempfile.mkdtemp(prefix="mb-notify-")
        r = notifier._send_file({}, tmp, "日报", "内容行")
        self.assertTrue(r["ok"])
        self.assertTrue(r["detail"].endswith(".md"))
        self.assertIn("notify", r["detail"])
        with open(r["detail"], encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("日报", content)


class TestDispatch(unittest.TestCase):
    def test_level_filter_and_isolation(self):
        tmp = _write_config(tempfile.mkdtemp(prefix="mb-notify-"), {
            "channels": [
                {"type": "desktop", "levels": ["critical", "warn"]},
                {"type": "file"},
            ]
        })
        # digest 级：desktop 被 level 过滤跳过，file 默认接收 digest
        res = notifier.send_notification(tmp, "t", "b", level="digest")
        self.assertTrue(res["desktop#0"]["skipped"])
        self.assertTrue(res["file#1"]["ok"])

        # 单渠道异常隔离：desktop 抛异常不影响 file
        with patch("lib.adapters.ops.notifier._send_desktop", side_effect=RuntimeError("boom")):
            res = notifier.send_notification(tmp, "t", "b", level="warn")
        self.assertFalse(res["desktop#0"]["ok"])
        self.assertIn("boom", res["desktop#0"]["error"])
        self.assertTrue(res["file#1"]["ok"])

    def test_disabled_and_unconfigured(self):
        tmp = _write_config(tempfile.mkdtemp(prefix="mb-notify-"), {"enabled": False, "channels": []})
        res = notifier.send_notification(tmp, "t", "b")
        self.assertTrue(res["skipped"]["ok"])

        tmp2 = tempfile.mkdtemp(prefix="mb-notify-")
        res2 = notifier.send_notification(tmp2, "t", "b")
        self.assertIn("no notify channels", res2["skipped"]["reason"])

    def test_per_channel_disabled(self):
        tmp = _write_config(tempfile.mkdtemp(prefix="mb-notify-"), {"channels": [
            {"type": "file", "enabled": False},
            {"type": "file"},
        ]})
        res = notifier.send_notification(tmp, "t", "b", level="digest")
        self.assertTrue(res["file#0"]["skipped"])
        self.assertIn("disabled", res["file#0"]["skipped"])
        self.assertTrue(res["file#1"]["ok"])

    def test_composition_facade(self):
        from lib.composition import send_notification

        tmp = _write_config(tempfile.mkdtemp(prefix="mb-notify-"), {"channels": [{"type": "file"}]})
        res = send_notification(tmp, "t", "b", level="digest")
        self.assertTrue(res["file#0"]["ok"])


if __name__ == "__main__":
    unittest.main()
