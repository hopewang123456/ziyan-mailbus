"""Tests for attachment upload API."""

import io
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from lib.api.handlers_attachments import handle_attachment_upload


class TestAttachmentUpload(unittest.TestCase):
    def test_upload_multipart(self):
        tmp = tempfile.mkdtemp()
        boundary = "----testboundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="note.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
            "hello attachment\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")

        handler = MagicMock()
        handler.data_dir = tmp
        handler.headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        }
        handler.rfile = io.BytesIO(body)
        sent = {}

        def _send_json(data, status=200):
            sent["data"] = data
            sent["status"] = status

        handler._send_json = _send_json
        handle_attachment_upload(handler)
        self.assertEqual(sent.get("status"), 201)
        ref = sent["data"]["ref"]
        self.assertTrue(ref.startswith("/mailbus/store/attachments/"))
        rel = ref.replace("/mailbus/store/", "")
        self.assertTrue(os.path.isfile(os.path.join(tmp, rel.replace("/", os.sep))))


if __name__ == "__main__":
    unittest.main()
