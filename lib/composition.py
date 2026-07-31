"""Composition root — wire ports to adapters."""
from __future__ import annotations

from dataclasses import dataclass, field

from lib.adapters.clock import DataPathRoot, FakeClock, SystemClock, UuidIdGenerator
from lib.adapters.config.file_repo import FileConfigRepository, build_config_repo
from lib.adapters.discovery import (
    DirDiscoverySource,
    DockerDiscoverySource,
    EnvDiscoverySource,
    build_default_sources,
)
from lib.ports.clock import Clock, IdGenerator, PathRoot
from lib.ports.config_repo import ConfigRepository
from lib.ports.discovery import DiscoverySource
from lib.ports.gates import AuditPort, HumanGatePort
from lib.ports.orchestration import BudgetMeterPort, NotifierPort, TaskFsmPort
from lib.ports.plane import ContainerPlanePort, HostPlanePort, MountMutex
from lib.ports.transport import MessageTransportPort


@dataclass
class AppContext:
    data_dir: str = ""
    discovery_sources: list[DiscoverySource] = field(default_factory=build_default_sources)
    clock: Clock = field(default_factory=SystemClock)
    ids: IdGenerator = field(default_factory=UuidIdGenerator)
    paths: PathRoot | None = None
    config_repo: ConfigRepository | None = None

    def ensure_paths(self) -> PathRoot:
        if self.paths is None:
            self.paths = DataPathRoot(self.data_dir or "store")
        return self.paths

    def ensure_config_repo(self) -> ConfigRepository:
        if self.config_repo is None:
            self.config_repo = build_config_repo(self.data_dir or "store")
        return self.config_repo


@dataclass
class PlaneBundle:
    host: HostPlanePort
    container: ContainerPlanePort
    mutex: MountMutex


@dataclass
class OrchestrationBundle:
    fsm: TaskFsmPort
    budget: BudgetMeterPort
    notifier: NotifierPort
    human_gate: HumanGatePort | None = None
    audit: AuditPort | None = None


@dataclass
class TransportBundle:
    messages: MessageTransportPort


_CTX: AppContext | None = None


def get_context() -> AppContext:
    global _CTX
    if _CTX is None:
        _CTX = AppContext()
    return _CTX


def set_context(ctx: AppContext) -> None:
    global _CTX
    _CTX = ctx


def reset_context() -> None:
    global _CTX
    _CTX = None


def bind_data_dir(data_dir: str) -> AppContext:
    """Attach PathRoot for data_dir on the process AppContext."""
    ctx = get_context()
    ctx.data_dir = data_dir
    ctx.paths = DataPathRoot(data_dir)
    ctx.config_repo = build_config_repo(data_dir)
    return ctx


def build_planes(data_dir: str, frameworks: dict | None = None) -> PlaneBundle:
    from lib.adapters.plane import build_container_plane, build_host_plane, build_mutex

    return PlaneBundle(
        host=build_host_plane(data_dir),
        container=build_container_plane(data_dir),
        mutex=build_mutex(frameworks),
    )


def build_orchestration(
    data_dir: str,
    *,
    with_human_gate: bool = True,
    with_file_audit: bool = True,
) -> OrchestrationBundle:
    import os

    from lib.adapters.orchestration import build_budget_meter, build_notifier, build_task_fsm
    from lib.adapters.orchestration.audit import FileAuditAdapter, NoopAudit
    from lib.adapters.orchestration.human_gate import HumanGateAdapter

    # MAILBUS_FILE_AUDIT=0|false|no|off disables file audit even when with_file_audit=True
    env_off = os.environ.get("MAILBUS_FILE_AUDIT", "1").strip().lower() in (
        "0", "false", "no", "off",
    )
    use_file_audit = bool(with_file_audit) and not env_off
    audit = FileAuditAdapter(data_dir) if use_file_audit else NoopAudit()
    human_gate = (
        HumanGateAdapter(data_dir, audit=audit) if with_human_gate else None
    )
    return OrchestrationBundle(
        fsm=build_task_fsm(),
        budget=build_budget_meter(data_dir),
        notifier=build_notifier(data_dir),
        human_gate=human_gate,
        audit=audit,
    )


def build_transport(data_dir: str, config: dict | None = None) -> MessageTransportPort:
    from lib.adapters.transport import build_message_transport

    return build_message_transport(data_dir, config)


__all__ = [
    "AppContext",
    "DirDiscoverySource",
    "DockerDiscoverySource",
    "EnvDiscoverySource",
    "FileConfigRepository",
    "OrchestrationBundle",
    "PlaneBundle",
    "TransportBundle",
    "bind_data_dir",
    "build_config_repo",
    "build_orchestration",
    "build_planes",
    "build_transport",
    "FakeClock",
    "get_context",
    "reset_context",
    "set_context",
]
