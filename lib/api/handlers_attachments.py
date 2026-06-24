"""POST /api/attachments/upload — human-queue 附件落盘。"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone

MAX_BYTES = 20 * 1024 * 1024


def _parse_multipart_file(body: bytes, content_type: str):
    m = re.search(r"boundary=([^;\s]+)", content_type or "")
    if not m:
        return None, None
    boundary = m.group(1).strip().strip('"').encode("ascii", "ignore")
    marker = b"--" + boundary
    parts = body.split(marker)
    for part in parts:
        if not part or part in (b"--", b"--\r\n", b"\r\n"):
            continue
        chunk = part
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        if chunk.endswith(b"--"):
            chunk = chunk[:-2]
        header_blob, _, payload = chunk.partition(b"\r\n\r\n")
        headers = header_blob.decode("utf-8", "ignore")
        if 'name="file"' not in headers:
            continue
        fn_match = re.search(r'filename="([^"]+)"', headers)
        filename = fn_match.group(1) if fn_match else "upload.bin"
        if payload.endswith(b"\r\n"):
            payload = payload[:-2]
        return filename, payload
    return None, None


def handle_attachment_upload(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0 or length > MAX_BYTES:
        handler._send_json({"error": "invalid_content_length"}, 400)
        return
    ctype = handler.headers.get("Content-Type") or ""
    if "multipart/form-data" not in ctype:
        handler._send_json({"error": "multipart_required"}, 400)
        return

    body = handler.rfile.read(length)
    raw_name, data = _parse_multipart_file(body, ctype)
    if not raw_name or data is None:
        handler._send_json({"error": "missing_file"}, 400)
        return

    raw_name = os.path.basename(raw_name.replace("\\", "/"))
    if not raw_name or raw_name in (".", ".."):
        handler._send_json({"error": "invalid_filename"}, 400)
        return
    if len(data) > MAX_BYTES:
        handler._send_json({"error": "file_too_large"}, 400)
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    uid = uuid.uuid4().hex[:12]
    rel_dir = os.path.join("attachments", stamp, uid)
    abs_dir = os.path.join(handler.data_dir, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    abs_path = os.path.join(abs_dir, raw_name)
    with open(abs_path, "wb") as f:
        f.write(data)

    docker_ref = f"/mailbus/store/{rel_dir}/{raw_name}".replace("\\", "/")
    handler._send_json({
        "status": "ok",
        "ref": docker_ref,
        "path": abs_path,
        "size": len(data),
        "label": raw_name,
    }, 201)
