"""Shared domain DTOs (immutable where practical)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, TypedDict


@dataclass(frozen=True)
class AgentRef:
    agent_id: str
    framework: str
    role_id: str = ""
    mount: str = ""
    enabled: bool = False


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    agent_id: str
    detail: str = ""
    latency_ms: int = 0


@dataclass(frozen=True)
class HealthStatus:
    agent_id: str
    state: str  # up|down|unknown|degraded
    detail: str = ""


@dataclass(frozen=True)
class SpawnHandle:
    agent_id: str
    session_id: str
    pid: int | None = None
    msg_id: str = ""


@dataclass(frozen=True)
class DiscoveredAgent:
    agent_id: str
    framework: str
    source: str
    home_path: str = ""
    binary_path: str = ""
    meta: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StepRef:
    task_id: str
    step_id: str
    attempt: int = 1


@dataclass(frozen=True)
class StepResult:
    step: StepRef
    agent_id: str
    status: str
    path: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OutboundMessage:
    agent_id: str
    msg_id: str
    body_path: str
    contract_path: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TransportReceipt:
    msg_id: str
    accepted: bool
    detail: str = ""
    channel: str = ""
    error_code: str = ""


@dataclass(frozen=True)
class ClientContext:
    remote_addr: str
    authorization: str = ""
    api_key_header: str = ""


class AuthDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class PlaneActionResult:
    ok: bool
    framework: str
    detail: str = ""


class IntegrationItemView(TypedDict, total=False):
    """Public API row for GET /api/settings/integrations."""

    name: str
    kind: str
    description: str


class IntegrationsOverviewView(TypedDict, total=False):
    """Public API body for integrations overview (D2 — avoid raw dict drift)."""

    ok: bool
    count: int
    integrations: list[IntegrationItemView]
    note: str
    data_dir: str


class SettingsSectionsView(TypedDict, total=False):
    """Public API body for GET /api/settings/sections."""

    status: str
    sections: list[str]
