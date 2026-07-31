"""Mount mutex: container|host exclusive per framework."""
from __future__ import annotations

from lib.domain.errors import Fatal


class FileMountMutex:
    """Config-backed mutex: frameworks[id].mount_mode must match requested mount."""

    def __init__(self, frameworks: dict | None = None):
        self.frameworks = frameworks or {}

    def assert_exclusive(self, framework: str, mount: str) -> None:
        if mount not in ("container", "host"):
            raise Fatal(f"invalid mount_mode: {mount}", code="fatal")
        entry = self.frameworks.get(framework) or {}
        current = str(entry.get("mount_mode") or "").strip()
        active = bool(entry.get("enabled") or entry.get("pending_enable"))
        if active and current and current != mount:
            raise Fatal(
                f"mount mutex: {framework} is on {current}; disable before {mount}",
                code="fatal",
            )
