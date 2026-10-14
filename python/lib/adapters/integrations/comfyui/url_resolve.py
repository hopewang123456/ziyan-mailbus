"""ComfyUI base URL 解析 — Windows 上 localhost 常不可达 WSL 端口，自动探测 WSL IP。"""

from __future__ import annotations

import os
import platform
import subprocess
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Iterable, List


def _probe(url: str, *, timeout: float = 8.0) -> bool:
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/system_stats", method="GET")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return False


def wsl_host_ip() -> str | None:
    if platform.system() != "Windows":
        return None
    try:
        proc = subprocess.run(
            ["wsl", "hostname", "-I"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        if proc.returncode != 0:
            return None
        first = (proc.stdout or "").strip().split()
        return first[0] if first else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _candidate_urls(explicit: str | None = None) -> List[str]:
    port = os.environ.get("COMFYUI_PORT") or "8188"
    seen: set[str] = set()
    out: List[str] = []

    def add(url: str) -> None:
        u = url.rstrip("/")
        if u and u not in seen:
            seen.add(u)
            out.append(u)

    # localhost 优先（WSL mirrored / port-forward 稳定）；显式 env 放最后避免 stale WSL IP
    add(f"http://127.0.0.1:{port}")
    wsl_ip = wsl_host_ip()
    if wsl_ip:
        add(f"http://{wsl_ip}:{port}")
    if explicit:
        add(explicit)
    return out


def find_working_comfyui_base_url(*, retries: int = 3, pause: float = 6.0) -> str | None:
    """探测并返回第一个可达 URL；Windows 上 localhost 可达时优先返回。"""
    import time

    port = os.environ.get("COMFYUI_PORT") or "8188"
    localhost = f"http://127.0.0.1:{port}"
    explicit = (os.environ.get("COMFYUI_BASE_URL") or "").strip() or None
    candidates = _candidate_urls(explicit)
    for attempt in range(max(1, retries)):
        for url in candidates:
            if _probe(url):
                if platform.system() == "Windows" and url != localhost and _probe(localhost):
                    return localhost
                return url
        if attempt + 1 < retries:
            time.sleep(pause)
    return None


@lru_cache(maxsize=1)
def resolve_comfyui_base_url(*, probe: bool = True) -> str:
    """返回可用的 ComfyUI base URL；probe=True 时依次探测。"""
    if probe:
        found = find_working_comfyui_base_url()
        if found:
            return found
    explicit = (os.environ.get("COMFYUI_BASE_URL") or "").strip() or None
    candidates = _candidate_urls(explicit)
    return candidates[0] if candidates else "http://127.0.0.1:8188"


def iter_candidate_urls() -> Iterable[str]:
    """供 sync 脚本列出候选（不缓存）。"""
    explicit = (os.environ.get("COMFYUI_BASE_URL") or "").strip() or None
    return _candidate_urls(explicit)
