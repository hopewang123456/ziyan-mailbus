"""Composition root — wire ports to adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lib.infra.clock import DataPathRoot, FakeClock, SystemClock, UuidIdGenerator
from lib.adapters.config.composite_config import CompositeConfigRepo, build_config_repo
from lib.adapters.config.file_repo import FileConfigRepository
from lib.adapters.discovery import (
    DirDiscoverySource,
    DockerDiscoverySource,
    EnvDiscoverySource,
    build_default_sources,
)
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
            self.ops = build_ops()
        return self.ops

    def ensure_integrations(self) -> IntegrationsPort:
        if self.integrations is None:
            self.integrations = get_integrations()
        return self.integrations

    def ensure_locale(self) -> LocalePort:
        if self.locale is None:
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


def get_fsm() -> TaskFsmPort:
    """Stateless TaskFsmPort (composition entry for application)."""
    from lib.adapters.orchestration import build_task_fsm

    return build_task_fsm()


def get_human_gate(data_dir: str, *, audit: AuditPort | None = None) -> HumanGatePort:
    """HumanGatePort bound to data_dir (composition entry for application)."""
    from lib.adapters.orchestration import build_human_gate

    return build_human_gate(data_dir, audit=audit)


def build_result_store(data_dir: str) -> ResultStorePort:
    from lib.adapters.results.msg_results import FileResultStore

    return FileResultStore(data_dir)


def get_token_store() -> Any:
    """Token persistence module (AuthPort backing store)."""
    from lib.adapters.config import token_store

    return token_store


def get_integrations() -> IntegrationsPort:
    from lib.adapters.integrations.port_adapter import PluginIntegrationsAdapter

    return PluginIntegrationsAdapter()


def build_ops() -> OpsPort:
    from lib.adapters.ops import build_ops as _build

    return _build()


def build_locale_port(data_dir: str = "", lang: str = "zh") -> LocalePort:
    from lib.adapters.locale import build_locale

    return build_locale(data_dir=data_dir, lang=lang)


def get_locale(data_dir: str = "", lang: str = "zh") -> LocalePort:
    """LocalePort for application (composition entry)."""
    ctx = get_context()
    if data_dir and data_dir != (ctx.data_dir or ""):
        return build_locale_port(data_dir, lang=lang)
    if ctx.locale is None or (data_dir and not ctx.data_dir):
        if data_dir:
            ctx.data_dir = data_dir
        ctx.locale = build_locale_port(ctx.data_dir or data_dir or "store", lang=lang)
    return ctx.locale


def build_transport(data_dir: str, config: dict | None = None) -> MessageTransportPort:
    from lib.adapters.transport import build_message_transport

    return build_message_transport(data_dir, config)


def build_bridged_agent(data_dir: str, config: dict | None = None) -> BridgedAgentPort:
    from lib.adapters.transport.bridge import CliBridgedAgent

    return CliBridgedAgent(data_dir=data_dir, config=config or {})


def build_a2a_transport(data_dir: str, config: dict | None = None) -> A2ATransportPort:
    """Production A2ATransportPort (HTTP A2A cancel/stream/poll + send)."""
    from lib.adapters.transport.http_a2a import HttpA2AMessageTransport

    return HttpA2AMessageTransport(data_dir=data_dir, config=config)


def build_transport_bundle(data_dir: str, config: dict | None = None) -> TransportBundle:
    a2a = build_a2a_transport(data_dir, config)
    return TransportBundle(
        messages=build_transport(data_dir, config),
        bridged=build_bridged_agent(data_dir, config),
        a2a=a2a,
    )


def complete_llm(messages: list, cfg: dict, *, prefer: str | None = None):
    """Lazy Internal LLM complete (composition entry for application)."""
    from lib.adapters.internal_llm.client import complete

    return complete(messages, cfg, prefer=prefer)


def retrieve_context(
    data_dir: str,
    cfg: dict | None,
    query: str,
    *,
    top_k: int = 8,
) -> list[dict]:
    """Lazy RAG retrieve (composition entry for application)."""
    from lib.adapters.internal_llm.index import retrieve

    return retrieve(data_dir, cfg, query, top_k=top_k)


def resolve_llm_config(raw: dict) -> dict:
    """Resolve mailbus_internal_llm config (env keys, defaults)."""
    from lib.adapters.internal_llm.config_resolve import resolve_llm_config as _resolve

    return _resolve(raw)


def llm_error_type():
    """Return LLMError exception class (for except clauses)."""
    from lib.adapters.internal_llm.client import LLMError

    return LLMError


def run_init_store(data_dir: str, *, fresh: bool = False) -> int:
    from lib.adapters.config.init_store import run_init_store as _run

    return _run(data_dir, fresh=fresh)


def run_merge_store_config(data_dir: str, *, quiet: bool = False) -> int:
    from lib.adapters.config.init_store import run_merge_store_config as _run

    return _run(data_dir, quiet=quiet)


def validate_config(config: dict) -> list[str]:
    from lib.adapters.config.config_schema import validate_config as _validate

    return _validate(config)


def scan_ack_files(data_dir: str, agents: dict) -> int:
    from lib.adapters.results.ack_handler import scan_ack_files as _scan

    return _scan(data_dir, agents)


def scan_forward_files(data_dir: str, agents: dict) -> int:
    from lib.adapters.results.ack_handler import scan_forward_files as _scan

    return _scan(data_dir, agents)


def scan_error_reports(data_dir: str, agents: dict) -> list:
    from lib.adapters.results.ack_handler import scan_error_reports as _scan

    return _scan(data_dir, agents)


def index_catalog(data_dir: str, agents: dict) -> Any:
    from lib.adapters.ops.catalog_search import index_catalog as _index

    return _index(data_dir, agents)


def search_catalog(data_dir: str, *, query_str: str = "", limit: int = 20) -> Any:
    from lib.adapters.ops.catalog_search import search_catalog as _search

    return _search(data_dir, query_str=query_str, limit=limit)


def search_all(
    data_dir: str,
    *,
    query_str: str = "",
    limit: int = 20,
    agents: dict | None = None,
) -> Any:
    from lib.adapters.ops.catalog_search import search_all as _search

    return _search(data_dir, query_str=query_str, limit=limit, agents=agents)


def get_ops() -> OpsPort:
    """OpsPort for application (composition entry)."""
    return get_context().ensure_ops()


def try_build_push_direct(*args: Any, **kwargs: Any) -> Any:
    from lib.adapters.frameworks.direct_push import try_build_push_direct as _build

    return _build(*args, **kwargs)


def parse_model_from_push_template(*args: Any, **kwargs: Any) -> Any:
    from lib.adapters.frameworks.direct_push import parse_model_from_push_template as _fn

    return _fn(*args, **kwargs)


def type_supports_auto_ack(agent_type: str) -> bool:
    from lib.adapters.frameworks import type_supports_auto_ack as _fn

    return bool(_fn(agent_type))


def store_path_for_agent(*args: Any, **kwargs: Any) -> Any:
    from lib.adapters.frameworks import store_path_for_agent as _fn

    return _fn(*args, **kwargs)


def agent_cli_active(*args: Any, **kwargs: Any) -> bool:
    from lib.adapters.frameworks import agent_cli_active as _fn

    return bool(_fn(*args, **kwargs))


def agent_cli_active_for(*args: Any, **kwargs: Any) -> bool:
    from lib.adapters.frameworks import agent_cli_active_for as _fn

    return bool(_fn(*args, **kwargs))


def resolve_push_cli(*args: Any, **kwargs: Any) -> Any:
    from lib.adapters.frameworks import resolve_push_cli as _fn

    return _fn(*args, **kwargs)


def should_mark_processing_on_push(*args: Any, **kwargs: Any) -> bool:
    from lib.adapters.frameworks import should_mark_processing_on_push as _fn

    return bool(_fn(*args, **kwargs))


def push_timeout_for(*args: Any, **kwargs: Any) -> int:
    from lib.adapters.frameworks import push_timeout_for as _fn

    return int(_fn(*args, **kwargs))


def launch_queue_prefix() -> str:
    from lib.adapters.frameworks.claude_launch import LAUNCH_QUEUE_PREFIX

    return LAUNCH_QUEUE_PREFIX


def enqueue_launch_queue(*args: Any, **kwargs: Any) -> bool:
    from lib.adapters.frameworks.claude_launch import enqueue_launch_queue as _fn

    return bool(_fn(*args, **kwargs))


def human_queue_path(data_dir: str) -> str:
    from lib.adapters.orchestration.human_queue import queue_path

    return queue_path(data_dir)


def is_phantom_reply_text(*args: Any, **kwargs: Any) -> bool:
    from lib.adapters.orchestration.phantom_detect import is_phantom_reply_text as _fn

    return bool(_fn(*args, **kwargs))


def should_auto_approve_plan(*args: Any, **kwargs: Any) -> bool:
    from lib.adapters.orchestration.automation import should_auto_approve_plan as _fn

    return bool(_fn(*args, **kwargs))


def list_unacked(*args: Any, **kwargs: Any) -> list:
    from lib.adapters.results.ack import list_unacked as _fn

    return list(_fn(*args, **kwargs))


def get_agent_profile(*args: Any, **kwargs: Any) -> Any:
    from lib.adapters.config.profile_registry import get_profile

    return get_profile(*args, **kwargs)


def resolve_config_path(*args: Any, **kwargs: Any) -> Any:
    from lib.adapters.config.config_files import resolve_config_path as _fn

    return _fn(*args, **kwargs)


def warn_if_config_missing(*args: Any, **kwargs: Any) -> None:
    from lib.adapters.config.config_files import warn_if_missing as _fn

    _fn(*args, **kwargs)


def merge_launch_desktop(*args: Any, **kwargs: Any) -> Any:
    from lib.adapters.frameworks.desktop_launch import merge_launch_desktop as _fn

    return _fn(*args, **kwargs)


def build_fake_ports() -> dict[str, Any]:
    """Dry-run / test doubles for new ports (Wave4)."""
    from lib.adapters.fakes import (
        FakeA2ATransport,
        FakeBridgedAgent,
        FakeIntegrations,
        FakeOps,
        FakeResultStore,
        FakeRuntime,
    )

    return {
        "runtime": FakeRuntime(),
        "result_store": FakeResultStore(),
        "a2a": FakeA2ATransport(),
        "bridged": FakeBridgedAgent(),
        "ops": FakeOps(),
        "integrations": FakeIntegrations(),
    }


__all__ = [
    "AppContext",
    "DirDiscoverySource",
    "DockerDiscoverySource",
    "EnvDiscoverySource",
    "CompositeConfigRepo",
    "FileConfigRepository",
    "OrchestrationBundle",
    "PlaneBundle",
    "TransportBundle",
    "agent_cli_active",
    "agent_cli_active_for",
    "bind_data_dir",
    "build_a2a_transport",
    "build_bridged_agent",
    "build_config_repo",
    "build_fake_ports",
    "build_locale_port",
    "build_ops",
    "build_orchestration",
    "build_planes",
    "build_result_store",
    "build_transport",
    "build_transport_bundle",
    "complete_llm",
    "enqueue_launch_queue",
    "FakeClock",
    "get_agent_profile",
    "get_context",
    "get_fsm",
    "get_human_gate",
    "get_integrations",
    "get_locale",
    "get_ops",
    "get_token_store",
    "human_queue_path",
    "index_catalog",
    "is_phantom_reply_text",
    "launch_queue_prefix",
    "list_unacked",
    "llm_error_type",
    "merge_launch_desktop",
    "parse_model_from_push_template",
    "push_timeout_for",
    "reset_context",
    "resolve_config_path",
    "resolve_llm_config",
    "resolve_push_cli",
    "retrieve_context",
    "run_init_store",
    "run_merge_store_config",
    "scan_ack_files",
    "scan_error_reports",
    "scan_forward_files",
    "search_all",
    "search_catalog",
    "set_context",
    "should_auto_approve_plan",
    "should_mark_processing_on_push",
    "store_path_for_agent",
    "try_build_push_direct",
    "type_supports_auto_ack",
    "validate_config",
    "warn_if_config_missing",
]
