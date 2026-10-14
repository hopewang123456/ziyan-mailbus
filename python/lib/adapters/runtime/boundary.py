"""Cross-boundary helpers — WSL↔Windows as LAN-like test bed (not real LAN delivery)."""

from __future__ import annotations

# Pairs where loopback on mailbus side must not be assumed reachable for agent services.
_CROSS = {
    ("windows", "wsl"),
    ("wsl", "windows"),
    ("windows", "linux"),
    ("linux", "windows"),
    ("wsl", "linux"),
    ("linux", "wsl"),
    ("windows", "docker"),
    ("wsl", "docker"),
    ("linux", "docker"),
    ("docker", "windows"),
    ("docker", "wsl"),
    ("docker", "linux"),
}


def is_cross_boundary(mailbus_runtime: str, agent_run_target: str) -> bool:
    a = (mailbus_runtime or "").strip().lower()
    b = (agent_run_target or "").strip().lower()
    if not a or not b or a == b:
        return False
    return (a, b) in _CROSS


def loopback_safe_for_peer(mailbus_runtime: str, agent_run_target: str) -> bool:
    """False when 127.0.0.1 on mailbus host may not reach the agent endpoint."""
    return not is_cross_boundary(mailbus_runtime, agent_run_target)


def peer_host_hint(mailbus_runtime: str, agent_run_target: str, *, wsl_ip: str = "") -> str:
    """Suggested host for probes/URLs across boundary (test bed)."""
    if loopback_safe_for_peer(mailbus_runtime, agent_run_target):
        return "127.0.0.1"
    a = (mailbus_runtime or "").lower()
    b = (agent_run_target or "").lower()
    if {a, b} == {"windows", "wsl"}:
        return (wsl_ip or "").strip() or "wsl.localhost"
    if b == "docker":
        return "127.0.0.1"  # published ports on host; still mark cross for awareness
    return (wsl_ip or "").strip() or "127.0.0.1"
