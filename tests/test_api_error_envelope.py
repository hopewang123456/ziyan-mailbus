"""API error envelope always includes error_code + message_zh."""
from __future__ import annotations

from lib.api.base import MailbusAPIHandler


class _H(MailbusAPIHandler):
    def __init__(self):
        self._buf = b""
        self._status = None
        self._headers = {}

    def send_response(self, code, message=None):
        self._status = code

    def send_header(self, k, v):
        self._headers[k] = v

    def end_headers(self):
        pass

    @property
    def wfile(self):
        class W:
            def __init__(self, outer):
                self.outer = outer

            def write(self, data):
                self.outer._buf = data

        return W(self)


def test_send_json_error_injects_code_and_zh():
    import json

    h = _H()
    h._send_json({"error": "not_found"}, 404)
    body = json.loads(h._buf.decode("utf-8"))
    assert h._status == 404
    assert body["error_code"] == "not_found"
    assert body["message_zh"]
    assert body["error"] == "not_found"


def test_send_json_ok_unchanged():
    import json

    h = _H()
    h._send_json({"status": "ok"}, 200)
    body = json.loads(h._buf.decode("utf-8"))
    assert body == {"status": "ok"}
    assert "error_code" not in body
