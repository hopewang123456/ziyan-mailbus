"""Lightweight health helpers (no adapter deps)."""
from __future__ import annotations


def probe_http(url: str, timeout: float = 3.0) -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 500
    except Exception:
        return False
