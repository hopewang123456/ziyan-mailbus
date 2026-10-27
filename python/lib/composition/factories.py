"""Composition root — true factories (R2 split from composition.py).

build_*/get_* wiring functions; bundles come from `context.py`.
"""
from __future__ import annotations

from typing import Any

from lib.interfaces.gates import AuditPort, HumanGatePort
from lib.interfaces.locale import LocalePort
from lib.interfaces.orchestration import TaskFsmPort
from lib.interfaces.results import ResultStorePort
from lib.interfaces.message_transport import (
    A2ATransportPort,
    BridgedAgentPort,
    MessageTransportPort,
)
from lib.composition.context import AppContext, PlaneBundle, OrchestrationBundle, TransportBundle, get_context


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
    from lib.adapters.orchestration.human_gate import HumanGateAdapter
    from lib.composition.assembler import assemble
    from lib.interfaces.assembler import registered_impls

    # L3（P0c）：audit 实现经装配器查表 — composition.audit 声明优先，
    # legacy MAILBUS_FILE_AUDIT=0 与 with_file_audit 参数仅作用于缺省值（渐进兼容）。
    env_off = os.environ.get("MAILBUS_FILE_AUDIT", "1").strip().lower() in (
        "0", "false", "no", "off",
    )
    default_audit = "file" if (with_file_audit and not env_off) else "noop"
    if "noop" not in registered_impls("audit"):  # 触发 adapters 登记加载
        import lib.adapters.orchestration.audit  # noqa: F401
    audit = assemble("audit", data_dir, default=default_audit)
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


def get_integrations():
    from lib.adapters.integrations.port_adapter import PluginIntegrationsAdapter

    return PluginIntegrationsAdapter()


def build_ops():
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


def get_ops():
    """OpsPort for application (composition entry)."""
    return get_context().ensure_ops()


def build_fake_ports() -> dict[str, Any]:
    """Dry-run / test doubles for new ports (Wave4)."""
    from lib.adapters.fakes import (
        FakeA2ATransport,
        FakeBridgedAgent,
        FakeIntegrations,
        FakeOps,
        FakeResultStore,
        FakeRuntime,
        FakeMessageTransport,
    )

    return {
        "runtime": FakeRuntime(),
        "result_store": FakeResultStore(),
        "a2a": FakeA2ATransport(),
        "bridged": FakeBridgedAgent(),
        "ops": FakeOps(),
        "integrations": FakeIntegrations(),
        "messages": FakeMessageTransport(),
    }


__all__ = [
    "build_planes",
    "build_orchestration",
    "get_fsm",
    "get_human_gate",
    "build_result_store",
    "get_token_store",
    "get_integrations",
    "build_ops",
    "build_locale_port",
    "get_locale",
    "build_transport",
    "build_bridged_agent",
    "build_a2a_transport",
    "build_transport_bundle",
    "get_ops",
    "build_fake_ports",
]
