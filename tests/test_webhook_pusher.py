"""
ziyan-mailbus Webhook 推送测试

使用 http.server 模拟 Webhook 服务端来测试推送流程。
"""
import os
import sys
import json
import threading
import tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.webhook_pusher import push_via_webhook
from lib.models import Message, MsgStatus
from lib.utils import _now_iso


# ── 模拟 Webhook 服务 ──────────────────────────────────────────────────

_webhook_store = {"requests": [], "status": 200, "delay": 0}


class _MockWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        _webhook_store["requests"].append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": json.loads(body),
        })
        self.send_response(_webhook_store.get("status", 200))
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def log_message(self, fmt, *args):
        pass  # 静默


def _run_server(port=0):
    server = HTTPServer(("127.0.0.1", port), _MockWebhookHandler)
    _webhook_store["server"] = server
    _webhook_store["port"] = server.server_address[1]  # 保存实际端口
    server.serve_forever()


def _setup_server(port=0):
    _webhook_store.clear()
    _webhook_store["requests"] = []
    _webhook_store["status"] = 200
    _webhook_store["port"] = port
    t = threading.Thread(target=_run_server, args=(port,), daemon=True)
    t.start()
    import time
    time.sleep(0.1)  # 等 server 启动
    actual_port = _webhook_store.get("port", port)
    return f"http://127.0.0.1:{actual_port}/webhook"


# ── 测试 ────────────────────────────────────────────────────────────────


class TestWebhookPusher:
    @classmethod
    def setup_class(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="mailbus_test_webhook_")
        cls.data_dir = f"{cls.tmpdir}/store"
        os.makedirs(f"{cls.data_dir}/inbox/test_agent", exist_ok=True)
        os.makedirs(f"{cls.data_dir}/errors", exist_ok=True)

    def _make_msg(self, msg_id: str, status=MsgStatus.PENDING) -> dict:
        return {
            "id": msg_id,
            "from": "test",
            "to": "test_agent",
            "priority": "normal",
            "type": "notice",
            "content": f"test {msg_id}",
            "attachments": [],
            "reply_format": {},
            "status": status,
            "pushed_count": 0,
            "created_at": _now_iso(),
        }

    def _write_inbox(self, messages: list):
        path = f"{self.data_dir}/inbox/test_agent/inbox.json"
        data = {
            "agent": "test_agent",
            "has_unread": True,
            "messages": messages,
            "since": _now_iso(),
        }
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False)

    def test_push_success(self):
        """Webhook 推送成功"""
        webhook_url = _setup_server()
        msgs = [self._make_msg("msg-wh-1")]
        self._write_inbox(msgs)

        failed = push_via_webhook(
            data_dir=self.data_dir,
            agent_name="test_agent",
            messages=msgs,
            webhook_url=webhook_url,
            max_retries=1,
        )
        assert failed == [], f"期望无失败，得到 {failed}"

        # 验证 webhook 收到请求
        assert len(_webhook_store["requests"]) >= 1
        req = _webhook_store["requests"][0]
        assert req["body"]["action"] == "push"
        assert req["body"]["agent"] == "test_agent"
        assert len(req["body"]["messages"]) == 1
        assert req["body"]["messages"][0]["id"] == "msg-wh-1"

    def test_push_with_signature(self):
        """Webhook 推送带 HMAC 签名"""
        webhook_url = _setup_server()
        msgs = [self._make_msg("msg-wh-sig-1")]

        failed = push_via_webhook(
            data_dir=self.data_dir,
            agent_name="test_agent",
            messages=msgs,
            webhook_url=webhook_url,
            webhook_secret="my-secret-key",
            max_retries=1,
        )
        assert failed == []
        req = _webhook_store["requests"][0]
        assert "X-Mailbus-Signature" in req["headers"]
        assert req["headers"]["X-Mailbus-Signature"].startswith("sha256=")

    def test_push_server_error_retry(self):
        """服务端返回 500，触发重试"""
        webhook_url = _setup_server()
        _webhook_store["status"] = 500
        msgs = [self._make_msg("msg-wh-fail-1")]

        failed = push_via_webhook(
            data_dir=self.data_dir,
            agent_name="test_agent",
            messages=msgs,
            webhook_url=webhook_url,
            max_retries=2,
        )
        assert len(failed) == 1  # 最终失败
        assert failed[0] == "msg-wh-fail-1"

        # 验证重试了 3 次（首次 + 2 次重试）
        assert len(_webhook_store["requests"]) == 3

    def test_push_empty_messages(self):
        """空消息列表"""
        webhook_url = _setup_server()
        failed = push_via_webhook(
            data_dir=self.data_dir,
            agent_name="test_agent",
            messages=[],
            webhook_url=webhook_url,
            max_retries=1,
        )
        assert failed == []


if __name__ == "__main__":
    cls = TestWebhookPusher()
    cls.setup_class()
    for _name in sorted(n for n in dir(cls) if n.startswith("test_")):
        getattr(cls, _name)()
        print(f"  ok {_name}")
    print("ok webhook_pusher")
