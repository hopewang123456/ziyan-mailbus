"""Transport 层共享类型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DispatchContext:
    data_dir: str
    task_id: str
    step_id: str
    to_agent: str
    role_type: int
    intent: str = ""
    msg_file: Optional[str] = None
    artifacts_in: list[dict[str, Any]] = field(default_factory=list)
    transport_policy: Optional[dict[str, Any]] = None
    force_transport: Optional[str] = None
    stub_fixture: Optional[str] = None


@dataclass
class DispatchResult:
    ok: bool
    transport_used: str
    a2a_task_id: Optional[str] = None
    step_result_path: Optional[str] = None
    transport_attempts: list[dict[str, Any]] = field(default_factory=list)
    a2a_retries_exhausted: bool = False
    awaiting_human: bool = False
    human_queue_payload: Optional[dict[str, Any]] = None
    error: Optional[str] = None
