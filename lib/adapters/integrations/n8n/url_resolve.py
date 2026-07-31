"""n8n base URL 解析 — Windows localhost 常不可达 WSL 端口。"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Iterable, List

from lib.adapters.integrations.comfyui.url_resolve import wsl_host_ip


def _probe(url: str, *, timeout: float = 8.0) -> bool:
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/", method="GET")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        pass
    # Windows NAT：WSL 内 n8n 可达但 localhost 不可达
    if url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:"):
        import platform
        import subprocess

        if platform.system() == "Windows":
            try:
                proc = subprocess.run(
                    ["wsl", "-e", "bash", "-lc", f"curl -sf --connect-timeout 3 {url.rstrip('/')}/ >/dev/null"],
                    capture_output=True,
                    timeout=12,
                    check=False,
                )
                return proc.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                return False
    return False


def _candidate_urls(explicit: str | None = None) -> List[str]:
    port = os.environ.get("N8N_PORT") or "5678"
    seen: set[str] = set()
    out: List[str] = []

    def add(url: str) -> None:
        u = url.rstrip("/")
        if u and u not in seen:
            seen.add(u)
            out.append(u)

    if explicit:
        add(explicit)
    add(f"http://127.0.0.1:{port}")
    wsl_ip = wsl_host_ip()
    if wsl_ip:
        add(f"http://{wsl_ip}:{port}")
    return out


def find_working_n8n_base_url(*, retries: int = 3, pause: float = 5.0) -> str | None:
    import time

    explicit = (os.environ.get("N8N_BASE_URL") or "").strip() or None
    candidates = _candidate_urls(explicit)
    for attempt in range(max(1, retries)):
        for url in candidates:
            if _probe(url):
                return url
        if attempt + 1 < retries:
            time.sleep(pause)
    return None


@lru_cache(maxsize=1)
def resolve_n8n_base_url(*, probe: bool = True) -> str:
    if probe:
        found = find_working_n8n_base_url()
        if found:
            return found
    explicit = (os.environ.get("N8N_BASE_URL") or "").strip() or None
    candidates = _candidate_urls(explicit)
    return candidates[0] if candidates else "http://127.0.0.1:5678"


def iter_candidate_urls() -> Iterable[str]:
    explicit = (os.environ.get("N8N_BASE_URL") or "").strip() or None
    return _candidate_urls(explicit)
