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


def process_ack_entry(data_dir: str, agent_name: str, ack_data: dict) -> bool:
    """单条 ack 立即处理（CLI ack 提交即生效，不等调度器）。"""
    from lib.adapters.results.ack_handler import process_ack as _process

    return _process(data_dir, agent_name, ack_data)


def process_mark_read_entry(data_dir: str, agent_name: str, mark_data: dict) -> bool:
    """单条 mark_read 立即处理。"""
    from lib.adapters.results.ack_handler import process_mark_read as _process

    return _process(data_dir, agent_name, mark_data)


def scan_forward_files(data_dir: str, agents: dict) -> int:
    from lib.adapters.results.ack_handler import scan_forward_files as _scan

    return _scan(data_dir, agents)


def scan_error_reports(data_dir: str, agents: dict) -> list:
    # 实际实现下沉到 application 层（2026-09 治理）；
    # adapter→application 跨层违规修复，composition 直接调 application 服务。
    from lib.application.orchestration.error_reports import scan_and_apply_error_reports

    return scan_and_apply_error_reports(data_dir, agents)


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


def is_task_complete(
    data_dir: str,
    agent_name: str,
    msg_entry: dict,
    *,
    agent_type: str = "",
    reply_text: str = "",
):
    """任务完成判定 — adapter 通过本函数拿到 application 服务，避免 adapter→application 跨层违规。

    实际实现见 `lib.application.orchestration.task_completion.is_task_complete`。
    """
    from lib.application.orchestration.task_completion import is_task_complete as _impl

    return _impl(
        data_dir, agent_name, msg_entry, agent_type=agent_type, reply_text=reply_text,
    )


def check_phantom_completion(*args: Any, **kwargs: Any):
    """Phantom completion 检测 — 委托给 adapter，adapter 通过 is_task_complete
    拿到 application 服务（composition 隔离跨层依赖）。"""
    from lib.adapters.orchestration.phantom_detect import check_phantom_completion as _fn

    return _fn(*args, **kwargs)


def resolve_human_queue_item(*args: Any, **kwargs: Any):
    """Human gate 队列项解析 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.human_queue_resolve.resolve_human_queue_item`。
    """
    from lib.application.orchestration.human_queue_resolve import resolve_human_queue_item as _impl

    return _impl(*args, **kwargs)


def effective_scan_interval_seconds(*args: Any, **kwargs: Any):
    """Token budget 动态 scan interval — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.integrations.token_budget.effective_scan_interval_seconds`。
    """
    from lib.application.integrations.token_budget import effective_scan_interval_seconds as _impl

    return _impl(*args, **kwargs)


def measure_mailbus_activity(*args: Any, **kwargs: Any):
    """Mailbus 活跃度测量 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.integrations.token_budget.measure_mailbus_activity`。
    """
    from lib.application.integrations.token_budget import measure_mailbus_activity as _impl

    return _impl(*args, **kwargs)


def get_system_message(*args: Any, **kwargs: Any):
    """新 agent 上线系统消息模板 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.commands.commands.get_system_message`。
    """
    from lib.application.commands.commands import get_system_message as _impl

    return _impl(*args, **kwargs)


def normalize_opencode_deliveries(*args: Any, **kwargs: Any):
    """OpenCode 交付归一化 — core/a2a 通过本函数拿到 application 服务。

    实际实现见 `lib.application.transport.delivery_normalizer.normalize_opencode_deliveries`。
    """
    from lib.application.transport.delivery_normalizer import normalize_opencode_deliveries as _impl

    return _impl(*args, **kwargs)


def attach_mailbus_routing(*args: Any, **kwargs: Any):
    """Mailbus 路由附加 — core/a2a 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.complexity_router.attach_mailbus_routing`。
    """
    from lib.adapters.orchestration.complexity_router import attach_mailbus_routing as _impl

    return _impl(*args, **kwargs)


def load_human_queue(*args: Any, **kwargs: Any):
    """Human queue 加载 — core/a2a 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.human_queue.load_queue`。
    """
    from lib.adapters.orchestration.human_queue import load_queue as _impl

    return _impl(*args, **kwargs)


def poll_pending_a2a_tasks(*args: Any, **kwargs: Any):
    """A2A 轮询 — core/a2a 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.a2a_poll.poll_pending_a2a_tasks`。
    """
    from lib.application.orchestration.a2a_poll import poll_pending_a2a_tasks as _impl

    return _impl(*args, **kwargs)


def get_harness(*args: Any, **kwargs: Any):
    """Harness 工厂 — core/a2a 通过本函数拿到 application 服务。

    实际实现见 `lib.application.harness.get_harness`。
    """
    from lib.application.harness import get_harness as _impl

    return _impl(*args, **kwargs)


def send_outbound(*args: Any, **kwargs: Any):
    """外发消息发送 — core/a2a 通过本函数拿到 application 服务。

    实际实现见 `lib.application.transport_send.send_outbound`。
    """
    from lib.application.transport_send import send_outbound as _impl

    return _impl(*args, **kwargs)


def message_zh(*args: Any, **kwargs: Any):
    """错误码中文消息 — core/a2a 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.locale.errors_zh.message_zh`。
    """
    from lib.adapters.locale.errors_zh import message_zh as _impl

    return _impl(*args, **kwargs)


def enqueue_human_queue(*args: Any, **kwargs: Any):
    """Human queue 入队 — core/a2a 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.human_queue.enqueue`。
    """
    from lib.adapters.orchestration.human_queue import enqueue as _impl

    return _impl(*args, **kwargs)


def ensure_framework_plugins_loaded(*args: Any, **kwargs: Any):
    """Framework 插件加载 — api 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.entry_point_discovery.ensure_framework_plugins_loaded`。
    """
    from lib.adapters.frameworks.entry_point_discovery import (
        ensure_framework_plugins_loaded as _impl,
    )

    return _impl(*args, **kwargs)


def ensure_integration_plugins_loaded(*args: Any, **kwargs: Any):
    """Integration 插件加载 — api 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.integrations.entry_point_discovery.ensure_integration_plugins_loaded`。
    """
    from lib.adapters.integrations.entry_point_discovery import (
        ensure_integration_plugins_loaded as _impl,
    )

    return _impl(*args, **kwargs)


def scheduler_hub_factory():
    """SchedulerHub 工厂 — api 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.scheduler.SchedulerHub`。
    """
    from lib.adapters.ops.scheduler import SchedulerHub

    return SchedulerHub


def apply_cancel(*args: Any, **kwargs: Any):
    """Task cancel — api/handlers_a2a 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.apply_cancel`。
    """
    from lib.adapters.orchestration.task_fsm import apply_cancel as _impl

    return _impl(*args, **kwargs)


def apply_pause(*args: Any, **kwargs: Any):
    """Task pause — api/handlers_tasks 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.apply_pause`。
    """
    from lib.adapters.orchestration.task_fsm import apply_pause as _impl

    return _impl(*args, **kwargs)


def apply_rollback(*args: Any, **kwargs: Any):
    """Task rollback — api/handlers_tasks 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.apply_rollback`。
    """
    from lib.adapters.orchestration.task_fsm import apply_rollback as _impl

    return _impl(*args, **kwargs)


def apply_skip(*args: Any, **kwargs: Any):
    """Task skip — api/handlers_tasks 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.apply_skip`。
    """
    from lib.adapters.orchestration.task_fsm import apply_skip as _impl

    return _impl(*args, **kwargs)


def apply_approve_join(*args: Any, **kwargs: Any):
    """Collab join_gate=review 管理者批准。"""
    from lib.adapters.orchestration.task_fsm import apply_approve_join as _impl

    return _impl(*args, **kwargs)


def ensure_fsm(*args: Any, **kwargs: Any):
    """Task FSM ensure — api/handlers_tasks 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.ensure_fsm`。
    """
    from lib.adapters.orchestration.task_fsm import ensure_fsm as _impl

    return _impl(*args, **kwargs)


def fsm_summary(*args: Any, **kwargs: Any):
    """Task FSM summary — api/handlers_tasks 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.fsm_summary`。
    """
    from lib.adapters.orchestration.task_fsm import fsm_summary as _impl

    return _impl(*args, **kwargs)


def mark_step_dispatched(*args: Any, **kwargs: Any):
    """Task step dispatch 标记 — api/handlers_tasks 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.orchestration.task_fsm.mark_step_dispatched`。
    """
    from lib.adapters.orchestration.task_fsm import mark_step_dispatched as _impl

    return _impl(*args, **kwargs)


def probe_all_internal_llm(*args: Any, **kwargs: Any):
    """Internal LLM probe — api/internal_llm_status 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.internal_llm.probe.probe_all`。
    """
    from lib.adapters.internal_llm.probe import probe_all as _impl

    return _impl(*args, **kwargs)


def load_llm_config_internal(*args: Any, **kwargs: Any):
    """Internal LLM 配置加载 — api/handlers_internal_llm 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.internal_llm.probe.load_llm_config`。
    """
    from lib.adapters.internal_llm.probe import load_llm_config as _impl

    return _impl(*args, **kwargs)


def rebuild_internal_llm_index(*args: Any, **kwargs: Any):
    """Internal LLM 索引重建 — api/handlers_internal_llm 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.internal_llm.index.rebuild_index`。
    """
    from lib.adapters.internal_llm.index import rebuild_index as _impl

    return _impl(*args, **kwargs)


def memory_bridge_module():
    """Memory bridge 集成模块 — api/handlers_device 通过本函数拿到 adapter 模块对象。

    实际模块见 `lib.adapters.integrations.memory_bridge`。
    调用方用法：`mb = composition.memory_bridge_module(); mb.write_memory_to_sqlite(...)`。
    """
    import lib.adapters.integrations.memory_bridge as _mod

    return _mod


def load_roles_for_instance(*args: Any, **kwargs: Any):
    """Roles for instance 加载 — api/handlers_lifecycle 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.instance_roles.load_roles_for_instance`。
    """
    from lib.adapters.config.instance_roles import load_roles_for_instance as _impl

    return _impl(*args, **kwargs)


def upsert_instance(*args: Any, **kwargs: Any):
    """Instance upsert — api/handlers_lifecycle 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.instance_roles.upsert_instance`。
    """
    from lib.adapters.config.instance_roles import upsert_instance as _impl

    return _impl(*args, **kwargs)


def discover_roles_for_instance(*args: Any, **kwargs: Any):
    """Discover roles for instance — api/handlers_lifecycle 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.instance_roles.discover_roles_for_instance`。
    """
    from lib.adapters.config.instance_roles import discover_roles_for_instance as _impl

    return _impl(*args, **kwargs)


def scan_agent_assets(*args: Any, **kwargs: Any):
    """Native scan agent assets — api/handlers_lifecycle 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.native_scan.scan_agent_assets`。
    """
    from lib.adapters.config.native_scan import scan_agent_assets as _impl

    return _impl(*args, **kwargs)


def clear_framework_discovery_cache(*args: Any, **kwargs: Any):
    """Framework discovery 缓存清理 — api/handlers_lifecycle 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.framework_discovery.clear_framework_discovery_cache`。
    """
    from lib.adapters.frameworks.framework_discovery import (
        clear_framework_discovery_cache as _impl,
    )

    return _impl(*args, **kwargs)


def framework_run_targets(*args: Any, **kwargs: Any):
    """Framework run targets — api/handlers_lifecycle 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.framework_discovery.framework_run_targets`。
    """
    from lib.adapters.frameworks.framework_discovery import framework_run_targets as _impl

    return _impl(*args, **kwargs)


def config_env_status(*args: Any, **kwargs: Any):
    """Config env status — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.config_admin.env_status`。
    """
    from lib.adapters.config.config_admin import env_status as _impl

    return _impl(*args, **kwargs)


def config_get_section(*args: Any, **kwargs: Any):
    """Config get section — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.config_admin.get_section`。
    """
    from lib.adapters.config.config_admin import get_section as _impl

    return _impl(*args, **kwargs)


def config_list_sections(*args: Any, **kwargs: Any):
    """Config list sections — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.config_admin.list_sections`。
    """
    from lib.adapters.config.config_admin import list_sections as _impl

    return _impl(*args, **kwargs)


def config_patch_env(*args: Any, **kwargs: Any):
    """Config patch env — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.config_admin.patch_env`。
    """
    from lib.adapters.config.config_admin import patch_env as _impl

    return _impl(*args, **kwargs)


def config_patch_section(*args: Any, **kwargs: Any):
    """Config patch section — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.config_admin.patch_section`。
    """
    from lib.adapters.config.config_admin import patch_section as _impl

    return _impl(*args, **kwargs)


def list_compose_files(*args: Any, **kwargs: Any):
    from lib.adapters.config.compose_files import list_compose_files as _impl

    return _impl(*args, **kwargs)


def read_compose_file(*args: Any, **kwargs: Any):
    from lib.adapters.config.compose_files import read_compose_file as _impl

    return _impl(*args, **kwargs)


def write_compose_file(*args: Any, **kwargs: Any):
    from lib.adapters.config.compose_files import write_compose_file as _impl

    return _impl(*args, **kwargs)


def build_skills_index_from_registry(*args: Any, **kwargs: Any):
    """Skills index build — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.sync_layers.build_skills_index_from_registry`。
    """
    from lib.adapters.config.sync_layers import build_skills_index_from_registry as _impl

    return _impl(*args, **kwargs)


def config_mailbus_root(data_dir: str = ""):
    """Agent registry mailbus root — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.agent_registry.mailbus_root`。
    """
    from lib.adapters.config.agent_registry import mailbus_root as _impl

    return _impl(data_dir)


def probe_service(*args: Any, **kwargs: Any):
    """Service probe — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.service_registry.probe_service`。
    """
    from lib.adapters.ops.service_registry import probe_service as _impl

    return _impl(*args, **kwargs)


def config_path(*args: Any, **kwargs: Any):
    """Config path — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.config_admin.config_path`。
    """
    from lib.adapters.config.config_admin import config_path as _impl

    return _impl(*args, **kwargs)


def reload_integration_plugins(*args: Any, **kwargs: Any):
    """Reload integration plugins — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.integrations.entry_point_discovery.reload_integration_plugins`。
    """
    from lib.adapters.integrations.entry_point_discovery import (
        reload_integration_plugins as _impl,
    )

    return _impl(*args, **kwargs)


# ── api/handlers_system.py 解耦（2026-09 治理）──────────────────────────


def load_heartbeat(*args: Any, **kwargs: Any):
    """Heartbeat status load — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.heartbeat.load_status`。
    """
    from lib.adapters.ops.heartbeat import load_status as _impl

    return _impl(*args, **kwargs)


def get_recent_alerts(*args: Any, **kwargs: Any):
    """Recent alerts — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.alerter.get_recent_alerts`。
    """
    from lib.adapters.ops.alerter import get_recent_alerts as _impl

    return _impl(*args, **kwargs)


def get_scheduler_status_sys(*args: Any, **kwargs: Any):
    """Scheduler status — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.scheduler.get_scheduler_status`。
    """
    from lib.adapters.ops.scheduler import get_scheduler_status as _impl

    return _impl(*args, **kwargs)


def running_in_mailbus_docker():
    """Platform runner in-docker — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.plane.platform_runner.running_in_mailbus_docker`。
    """
    from lib.adapters.plane.platform_runner import running_in_mailbus_docker as _impl

    return _impl()


def apply_instance_endpoint(*args: Any, **kwargs: Any):
    """Instance endpoint apply — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.runtime.cred_delivery.apply_instance_endpoint`。
    """
    from lib.adapters.runtime.cred_delivery import apply_instance_endpoint as _impl

    return _impl(*args, **kwargs)


def resolve_browser_url(*args: Any, **kwargs: Any):
    """Browser URL resolve — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.claude_browser_launch.resolve_browser_url`。
    """
    from lib.adapters.frameworks.claude_browser_launch import resolve_browser_url as _impl

    return _impl(*args, **kwargs)


def build_authed_url(*args: Any, **kwargs: Any):
    """Authed URL build — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.browser_auth.build_authed_url`。
    """
    from lib.adapters.config.browser_auth import build_authed_url as _impl

    return _impl(*args, **kwargs)


def resolve_agent_auth(*args: Any, **kwargs: Any):
    """Agent auth resolve — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.browser_auth.resolve_agent_auth`。
    """
    from lib.adapters.config.browser_auth import resolve_agent_auth as _impl

    return _impl(*args, **kwargs)


def agent_has_desktop(*args: Any, **kwargs: Any):
    """Has desktop check — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.desktop_launch.agent_has_desktop`。
    """
    from lib.adapters.frameworks.desktop_launch import agent_has_desktop as _impl

    return _impl(*args, **kwargs)


def get_agent(*args: Any, **kwargs: Any):
    """Agent get — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.agent_registry.get_agent`。
    """
    from lib.adapters.config.agent_registry import get_agent as _impl

    return _impl(*args, **kwargs)


def mailbus_root_sys(*args: Any, **kwargs: Any):
    """Mailbus root — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.agent_registry.mailbus_root`。
    """
    from lib.adapters.config.agent_registry import mailbus_root as _impl

    return _impl(*args, **kwargs)


def framework_status(*args: Any, **kwargs: Any):
    """Framework status — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.framework_discovery.framework_status`。
    """
    from lib.adapters.frameworks.framework_discovery import framework_status as _impl

    return _impl(*args, **kwargs)


def scan_framework_agents(*args: Any, **kwargs: Any):
    """Framework agents scan — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.framework_discovery.scan_framework_agents`。
    """
    from lib.adapters.frameworks.framework_discovery import scan_framework_agents as _impl

    return _impl(*args, **kwargs)


def redact_api_token(*args: Any, **kwargs: Any):
    """API token redact — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.config_admin._redact_api_token`。
    """
    from lib.adapters.config.config_admin import _redact_api_token as _impl

    return _impl(*args, **kwargs)


# ── api/handlers_system.py（ops.search / avatar / claude / clinic / locale）


def search(*args: Any, **kwargs: Any):
    """通用检索 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.search.search`。
    """
    from lib.adapters.ops.search import search as _impl

    return _impl(*args, **kwargs)


def list_external_tools_summary(*args: Any, **kwargs: Any):
    """外部工具汇总 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.catalog_search.list_external_tools_summary`。
    """
    from lib.adapters.ops.catalog_search import list_external_tools_summary as _impl

    return _impl(*args, **kwargs)


def is_online(*args: Any, **kwargs: Any):
    """心跳在线判定 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.heartbeat.is_online`。
    """
    from lib.adapters.ops.heartbeat import is_online as _impl

    return _impl(*args, **kwargs)


def resolve_avatar_urls(*args: Any, **kwargs: Any):
    """头像/插画 URL 解析 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.avatar_paths.resolve_avatar_urls`。
    """
    from lib.adapters.config.avatar_paths import resolve_avatar_urls as _impl

    return _impl(*args, **kwargs)


def resolve_animated_file(*args: Any, **kwargs: Any):
    """动效文件定位 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.avatar_paths.resolve_animated_file`。
    """
    from lib.adapters.config.avatar_paths import resolve_animated_file as _impl

    return _impl(*args, **kwargs)


def resolve_portrait_file(*args: Any, **kwargs: Any):
    """立绘文件定位 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.avatar_paths.resolve_portrait_file`。
    """
    from lib.adapters.config.avatar_paths import resolve_portrait_file as _impl

    return _impl(*args, **kwargs)


def openclaw_gateway_token(*args: Any, **kwargs: Any):
    """OpenClaw gateway token — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.browser_auth.openclaw_gateway_token`。
    """
    from lib.adapters.config.browser_auth import openclaw_gateway_token as _impl

    return _impl(*args, **kwargs)


def openclaw_adapter_class():
    """OpenClawAdapter class — api/handlers_system 通过本函数拿到 adapter 类。

    实际实现见 `lib.adapters.frameworks.OpenClawAdapter`。
    """
    from lib.adapters.frameworks import OpenClawAdapter as _impl

    return _impl


def resolve_port(*args: Any, **kwargs: Any):
    """launch port 解析 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.launch_ports.resolve_port`。
    """
    from lib.adapters.config.launch_ports import resolve_port as _impl

    return _impl(*args, **kwargs)


def launch_desktop(*args: Any, **kwargs: Any):
    """桌面启动 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.desktop_launch.launch_desktop`。
    """
    from lib.adapters.frameworks.desktop_launch import launch_desktop as _impl

    return _impl(*args, **kwargs)


def launch_claude_browser(*args: Any, **kwargs: Any):
    """Claude 浏览器启动 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.claude_browser_launch.launch_claude_browser`。
    """
    from lib.adapters.frameworks.claude_browser_launch import launch_claude_browser as _impl

    return _impl(*args, **kwargs)


def launch_claude_cli(*args: Any, **kwargs: Any):
    """Claude CLI 启动 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.claude_launch.launch_claude_cli`。
    """
    from lib.adapters.frameworks.claude_launch import launch_claude_cli as _impl

    return _impl(*args, **kwargs)


def list_clinic_tools(*args: Any, **kwargs: Any):
    """Clinic tool 清单 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.clinic_tools.list_clinic_tools`。
    """
    from lib.adapters.ops.clinic_tools import list_clinic_tools as _impl

    return _impl(*args, **kwargs)


def run_clinic_tool(*args: Any, **kwargs: Any):
    """Clinic tool 执行 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.clinic_tools.run_clinic_tool`。
    """
    from lib.adapters.ops.clinic_tools import run_clinic_tool as _impl

    return _impl(*args, **kwargs)


def run_doctor_checks(*args: Any, **kwargs: Any):
    """doctor 检查 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.ops.doctor_checks.run_doctor_checks`。
    """
    from lib.adapters.ops.doctor_checks import run_doctor_checks as _impl

    return _impl(*args, **kwargs)


def locale_catalog(*args: Any, **kwargs: Any):
    """locale catalog — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.locale.errors_zh.locale_catalog`。
    """
    from lib.adapters.locale.errors_zh import locale_catalog as _impl

    return _impl(*args, **kwargs)


def stable_codes_covered(*args: Any, **kwargs: Any):
    """locale 稳定码覆盖 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.locale.errors_zh.stable_codes_covered`。
    """
    from lib.adapters.locale.errors_zh import stable_codes_covered as _impl

    return _impl(*args, **kwargs)


def reload_framework_plugins(*args: Any, **kwargs: Any):
    """framework plugin reload — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.entry_point_discovery.discover_and_register_frameworks`
    （历史命名 `reload_framework_plugins`，行为为 discover + register）。
    """
    from lib.adapters.frameworks.entry_point_discovery import (
        discover_and_register_frameworks as _impl,
    )

    return _impl(*args, **kwargs)


def resolve_container(*args: Any, **kwargs: Any):
    """framework container 解析 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.registry.resolve_container`。
    """
    from lib.adapters.frameworks.registry import resolve_container as _impl

    return _impl(*args, **kwargs)


def framework_get_adapter(*args: Any, **kwargs: Any):
    """framework adapter 获取 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.registry.get_adapter`。
    """
    from lib.adapters.frameworks.registry import get_adapter as _impl

    return _impl(*args, **kwargs)


def supports_interactive_cli(*args: Any, **kwargs: Any):
    """framework interactive CLI 支持判定 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.registry.supports_interactive_cli`。
    """
    from lib.adapters.frameworks.registry import supports_interactive_cli as _impl

    return _impl(*args, **kwargs)


def build_interactive_cli_command(*args: Any, **kwargs: Any):
    """framework interactive CLI 命令构建 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.registry.build_interactive_cli_command`。
    """
    from lib.adapters.frameworks.registry import build_interactive_cli_command as _impl

    return _impl(*args, **kwargs)


def run_scan_once(*args: Any, **kwargs: Any):
    """bus scan 执行一轮 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.commands.commands.run_scan_once`。
    """
    from lib.application.commands.commands import run_scan_once as _impl

    return _impl(*args, **kwargs)


def task_tracker_factory():
    """TaskTracker 工厂 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.tracker.TaskTracker`。
    adapter 不直接 import tracker 子树（避免跨层违规）。
    """
    from lib.application.orchestration.tracker import TaskTracker

    return TaskTracker


def bridge_reconcile(*args: Any, **kwargs: Any):
    """Bridge 协调 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.workflow.intake.spawn_rules.bridge_reconcile`。
    """
    from lib.application.workflow.intake.spawn_rules import bridge_reconcile as _impl

    return _impl(*args, **kwargs)


def triage_inbox_anomaly(*args: Any, **kwargs: Any):
    """Inbox 异常分诊 — adapter 通过本函数拿到 application 服务。

    实际实现见 `lib.application.internal_llm.triage.triage_inbox_anomaly`。
    """
    from lib.application.internal_llm.triage import triage_inbox_anomaly as _impl

    return _impl(*args, **kwargs)


# ── task_fsm.py 跨层调用（adapter→application 解耦，2026-09 治理）────────────


def trigger_task(*args: Any, **kwargs: Any):
    """Pipeline 任务触发 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.pipeline.trigger.trigger_task`。
    """
    from lib.application.orchestration.pipeline.trigger import trigger_task as _impl

    return _impl(*args, **kwargs)


def resolve_next_assignee(*args: Any, **kwargs: Any):
    """Pipeline 下一步执行者解析 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.pipeline.routing.resolve_next_assignee`。
    """
    from lib.application.orchestration.pipeline.routing import resolve_next_assignee as _impl

    return _impl(*args, **kwargs)


def is_pipeline_terminal(*args: Any, **kwargs: Any):
    """Pipeline 终止判定 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.pipeline.routing.is_pipeline_terminal`。
    """
    from lib.application.orchestration.pipeline.routing import is_pipeline_terminal as _impl

    return _impl(*args, **kwargs)


def run_step_verify(*args: Any, **kwargs: Any):
    """Step verify 执行 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.ops.verify.runner.run_step_verify`。
    """
    from lib.application.ops.verify.runner import run_step_verify as _impl

    return _impl(*args, **kwargs)


def notify_verify_failure(*args: Any, **kwargs: Any):
    """Verify 失败升级通知 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.harness.escalation.notify_verify_failure`。
    """
    from lib.application.harness.escalation import notify_verify_failure as _impl

    return _impl(*args, **kwargs)


def block_for_clarifications(*args: Any, **kwargs: Any):
    """阻塞等待澄清 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.decomposition.block_for_clarifications`。
    """
    from lib.application.orchestration.decomposition import block_for_clarifications as _impl

    return _impl(*args, **kwargs)


def handle_design_step_decomposition(*args: Any, **kwargs: Any):
    """设计步骤拆解 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.decomposition.handle_design_step_decomposition`。
    """
    from lib.application.orchestration.decomposition import handle_design_step_decomposition as _impl

    return _impl(*args, **kwargs)


def maybe_block_after_step(*args: Any, **kwargs: Any):
    """Step 后置阻塞判定 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.workflow.engine.maybe_block_after_step`。
    """
    from lib.application.workflow.engine import maybe_block_after_step as _impl

    return _impl(*args, **kwargs)


def enter_accepting_or_succeed(*args: Any, **kwargs: Any):
    """进入 accepting 状态 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.actions.enter_accepting_or_succeed`。
    """
    from lib.application.orchestration.actions import enter_accepting_or_succeed as _impl

    return _impl(*args, **kwargs)


def get_next_role(*args: Any, **kwargs: Any):
    """下一角色判定 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.role_flow.get_next_role`。
    """
    from lib.application.orchestration.role_flow import get_next_role as _impl

    return _impl(*args, **kwargs)


def next_role_after(*args: Any, **kwargs: Any):
    """步骤内下一跳裁决（role-flow SoT 优先，legacy 兜底）— 跨层唯一入口。

    实际实现见 `lib.application.orchestration.role_flow.next_role_after`。
    """
    from lib.application.orchestration.role_flow import next_role_after as _impl

    return _impl(*args, **kwargs)


def pick_person_for_role(*args: Any, **kwargs: Any):
    """角色指派 agent 选择 — task_fsm 通过本函数拿到 application 服务。

    实际实现见 `lib.application.orchestration.role_flow.pick_person_for_role`。
    """
    from lib.application.orchestration.role_flow import pick_person_for_role as _impl

    return _impl(*args, **kwargs)


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
    "agent_has_desktop",
    "apply_approve_join",
    "apply_cancel",
    "apply_pause",
    "apply_rollback",
    "apply_skip",
    "ensure_fsm",
    "fsm_summary",
    "mark_step_dispatched",
    "attach_mailbus_routing",
    "bind_data_dir",
    "block_for_clarifications",
    "build_a2a_transport",
    "build_bridged_agent",
    "build_config_repo",
    "build_fake_ports",
    "build_locale_port",
    "build_skills_index_from_registry",
    "build_authed_url",
    "build_ops",
    "build_orchestration",
    "build_planes",
    "build_result_store",
    "build_transport",
    "build_transport_bundle",
    "check_phantom_completion",
    "clear_framework_discovery_cache",
    "complete_llm",
    "config_env_status",
    "config_get_section",
    "config_list_sections",
    "config_mailbus_root",
    "config_patch_env",
    "config_patch_section",
    "config_path",
    "framework_status",
    "framework_run_targets",
    "discover_roles_for_instance",
    "effective_scan_interval_seconds",
    "enqueue_human_queue",
    "build_interactive_cli_command",
    "enqueue_launch_queue",
    "ensure_framework_plugins_loaded",
    "ensure_integration_plugins_loaded",
    "enter_accepting_or_succeed",
    "FakeClock",
    "framework_run_targets",
    "framework_get_adapter",
    "get_agent",
    "get_agent_profile",
    "get_context",
    "get_fsm",
    "get_harness",
    "get_integrations",
    "get_locale",
    "get_next_role",
    "next_role_after",
    "get_ops",
    "get_recent_alerts",
    "get_scheduler_status_sys",
    "get_system_message",
    "get_token_store",
    "handle_design_step_decomposition",
    "human_queue_path",
    "index_catalog",
    "is_pipeline_terminal",
    "is_task_complete",
    "is_online",
    "launch_claude_browser",
    "launch_claude_cli",
    "launch_desktop",
    "launch_queue_prefix",
    "list_clinic_tools",
    "list_external_tools_summary",
    "list_unacked",
    "load_heartbeat",
    "load_human_queue",
    "load_llm_config_internal",
    "load_roles_for_instance",
    "locale_catalog",
    "llm_error_type",
    "maybe_block_after_step",
    "mailbus_root_sys",
    "measure_mailbus_activity",
    "memory_bridge_module",
    "merge_launch_desktop",
    "message_zh",
    "notify_verify_failure",
    "normalize_opencode_deliveries",
    "openclaw_adapter_class",
    "openclaw_gateway_token",
    "parse_model_from_push_template",
    "pick_person_for_role",
    "poll_pending_a2a_tasks",
    "probe_all_internal_llm",
    "probe_service",
    "push_timeout_for",
    "rebuild_internal_llm_index",
    "redact_api_token",
    "reload_framework_plugins",
    "reload_integration_plugins",
    "reset_context",
    "resolve_animated_file",
    "resolve_avatar_urls",
    "resolve_config_path",
    "resolve_container",
    "resolve_human_queue_item",
    "resolve_llm_config",
    "resolve_next_assignee",
    "resolve_port",
    "resolve_portrait_file",
    "resolve_push_cli",
    "resolve_agent_auth",
    "resolve_browser_url",
    "supports_interactive_cli",
    "retrieve_context",
    "run_clinic_tool",
    "run_doctor_checks",
    "run_init_store",
    "run_merge_store_config",
    "run_scan_once",
    "run_step_verify",
    "scan_ack_files",
    "scan_error_reports",
    "scan_forward_files",
    "scan_agent_assets",
    "scheduler_hub_factory",
    "search",
    "search_all",
    "search_catalog",
    "send_outbound",
    "set_context",
    "should_auto_approve_plan",
    "should_mark_processing_on_push",
    "stable_codes_covered",
    "store_path_for_agent",
    "task_tracker_factory",
    "trigger_task",
    "triage_inbox_anomaly",
    "try_build_push_direct",
    "type_supports_auto_ack",
    "upsert_instance",
    "list_compose_files",
    "read_compose_file",
    "write_compose_file",
    "validate_config",
    "warn_if_config_missing",
]
