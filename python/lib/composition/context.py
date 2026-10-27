"""Composition root — context & bundles (R2 split from composition.py).

AppContext / bundle dataclasses / process context management.
True factories live in `factories.py`; lazy cross-layer facades in `facade_*.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lib.adapters.config.composite_config import CompositeConfigRepo, build_config_repo
from lib.adapters.config.file_repo import FileConfigRepository
from lib.adapters.discovery import (
    DirDiscoverySource,
    DockerDiscoverySource,
    EnvDiscoverySource,
    build_default_sources,
)
from lib.infra.clock import DataPathRoot, FakeClock, SystemClock, UuidIdGenerator
from lib.interfaces.clock import Clock, IdGenerator, PathRoot
from lib.interfaces.config_repo import ConfigRepository
from lib.interfaces.discovery import DiscoverySource
from lib.interfaces.gates import AuditPort, HumanGatePort
from lib.interfaces.integrations import IntegrationsPort
from lib.interfaces.locale import LocalePort
from lib.interfaces.message_transport import (
    A2ATransportPort,
    BridgedAgentPort,
    MessageTransportPort,
)
from lib.interfaces.ops import OpsPort
from lib.interfaces.orchestration import BudgetMeterPort, NotifierPort, TaskFsmPort
from lib.interfaces.plane import ContainerPlanePort, HostPlanePort, MountMutex
from lib.interfaces.results import ResultStorePort


@dataclass
class AppContext:
    data_dir: str = ""
    discovery_sources: list[DiscoverySource] = field(default_factory=build_default_sources)
    clock: Clock = field(default_factory=SystemClock)
    ids: IdGenerator = field(default_factory=UuidIdGenerator)
    paths: PathRoot | None = None
    config_repo: ConfigRepository | None = None
    ops: OpsPort | None = None
    integrations: IntegrationsPort | None = None
    locale: LocalePort | None = None

    def ensure_paths(self) -> PathRoot:
        if self.paths is None:
            self.paths = DataPathRoot(self.data_dir or "store")
        return self.paths

    def ensure_config_repo(self) -> ConfigRepository:
        if self.config_repo is None:
            self.config_repo = build_config_repo(self.data_dir or "store")
        return self.config_repo

    def ensure_ops(self) -> OpsPort:
        if self.ops is None:
            from lib.composition.factories import build_ops
            self.ops = build_ops()
        return self.ops

    def ensure_integrations(self) -> IntegrationsPort:
        if self.integrations is None:
            from lib.composition.factories import get_integrations
            self.integrations = get_integrations()
        return self.integrations

    def ensure_locale(self) -> LocalePort:
        if self.locale is None:
            from lib.composition.factories import build_locale_port
            self.locale = build_locale_port(self.data_dir or "store")
        return self.locale


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
    bridged: BridgedAgentPort | None = None
    a2a: A2ATransportPort | None = None


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
    ctx.ops = None
    ctx.integrations = None
    ctx.locale = None
    try:
        from lib.adapters.frameworks.entry_point_discovery import ensure_framework_plugins_loaded
        from lib.adapters.integrations.entry_point_discovery import ensure_integration_plugins_loaded
        from lib.adapters.config.config_files import ensure_sensitive_config_files
        from lib.infra.constants import MAILBUS_ROOT

        ensure_sensitive_config_files(MAILBUS_ROOT)
        ensure_framework_plugins_loaded(data_dir=data_dir)
        ensure_integration_plugins_loaded(data_dir=data_dir)
    except Exception:
        pass
    return ctx


__all__ = [
    "AppContext",
    "PlaneBundle",
    "OrchestrationBundle",
    "TransportBundle",
    "get_context",
    "set_context",
    "reset_context",
    "bind_data_dir",
    # re-exports kept for backwards compatibility (原 composition.py 头部 re-export)
    "CompositeConfigRepo",
    "FileConfigRepository",
    "DirDiscoverySource",
    "DockerDiscoverySource",
    "EnvDiscoverySource",
    "FakeClock",
    "build_config_repo",
]
