"""Windows 原生 mailbus 访问 WSL Docker n8n 的桥接（NAT 模式下 localhost:5678 不可达）。"""
from __future__ import annotations

import json
import platform
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any


def _is_n8n_local_url(url: str) -> bool:
    u = (url or "").lower()
    return ":5678/" in u or u.endswith(":5678")


def post_json_via_wsl(url: str, payload: dict, *, timeout: int = 30, retries: int = 3) -> tuple[int, dict | str]:
    """经 WSL curl POST JSON，返回 (status, body)。"""
    last: tuple[int, dict | str] = (0, "wsl curl failed")
    for attempt in range(max(1, retries)):
        last = _post_json_via_wsl_once(url, payload, timeout=timeout)
        if last[0] and 200 <= last[0] < 300:
            return last
        if attempt + 1 < retries:
            time.sleep(2)
    return last


def _post_json_via_wsl_once(url: str, payload: dict, *, timeout: int = 30) -> tuple[int, dict | str]:
    body = json.dumps(payload, ensure_ascii=False)
    args = [
        "wsl",
        "-e",
        "curl",
        "-sS",
        "-o",
        "/tmp/mb-n8n-resp.json",
        "-w",
        "%{http_code}",
        "-X",
        "POST",
        url,
        "-H",
        "Content-Type: application/json",
        "-d",
        body,
        "--connect-timeout",
        str(min(timeout, 25)),
    ]
    proc = subprocess.run(
        args,
        capture_output=True,
        timeout=timeout + 15,
        check=False,
    )
    code_raw = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    digits = "".join(c for c in code_raw if c.isdigit())
    status = int(digits[-3:]) if len(digits) >= 3 else 0

    if proc.returncode != 0 and not status:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        if "curl:" in err:
            return 0, err.split("curl:")[-1].strip()[:200]

    read_proc = subprocess.run(
        ["wsl", "-e", "cat", "/tmp/mb-n8n-resp.json"],
        capture_output=True,
        timeout=15,
        check=False,
    )
    raw = (read_proc.stdout or b"").decode("utf-8", errors="replace").strip()
    if not raw:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        return status or 0, err or "wsl curl failed"
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def post_json_with_wsl_fallback(
    url: str,
    payload: dict,
    headers: dict | None = None,
    *,
    timeout: int = 30,
) -> tuple[int, dict | str]:
    """先直连；Windows 上 n8n localhost 失败则走 WSL curl。"""
    headers = headers or {"Content-Type": "application/json"}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    direct_failed = False
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        if platform.system() == "Windows" and _is_n8n_local_url(url) and exc.code in (404, 502, 503):
            return post_json_via_wsl(url, payload, timeout=timeout)
        return exc.code, parsed
    except (urllib.error.URLError, TimeoutError, OSError):
        direct_failed = True

    if direct_failed and platform.system() == "Windows" and _is_n8n_local_url(url):
        return post_json_via_wsl(url, payload, timeout=timeout)
    raise urllib.error.URLError("connection failed")
