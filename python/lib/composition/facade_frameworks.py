"""Composition facades — frameworks domain (R2 split from composition.py).

Target domain: adapters.frameworks.* (push / discovery / launch / registry).
"""
from __future__ import annotations

from typing import Any


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


def framework_push_template(framework: str) -> str:
    """外部框架（TemplateAdapter）的 push 模板原文——application 层取模板走此门面。"""
    from lib.adapters.frameworks.registry import get_adapter

    adapter = get_adapter(framework)
    return getattr(adapter, "push_template", "") or ""


def get_framework_spec(framework: str):
    """FrameworkSpec 单条查询（application 层读 descriptor 走此门面）。"""
    from lib.adapters.frameworks.spec import FRAMEWORKS

    return FRAMEWORKS.get((framework or "").strip())


def list_framework_types() -> tuple[tuple, tuple]:
    """(内置类型 tuple, 全部类型 tuple)——type 校验/提示用。"""
    from lib.adapters.frameworks.spec import FRAMEWORKS

    return (
        tuple(fw for fw, s in FRAMEWORKS.items() if s.in_agent_types),
        tuple(FRAMEWORKS),
    )


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


def ensure_framework_plugins_loaded(*args: Any, **kwargs: Any):
    """Framework 插件加载 — api 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.entry_point_discovery.ensure_framework_plugins_loaded`。
    """
    from lib.adapters.frameworks.entry_point_discovery import (
        ensure_framework_plugins_loaded as _impl,
    )

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


def resolve_browser_url(*args: Any, **kwargs: Any):
    """Browser URL resolve — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.claude_browser_launch.resolve_browser_url`。
    """
    from lib.adapters.frameworks.claude_browser_launch import resolve_browser_url as _impl

    return _impl(*args, **kwargs)


def agent_has_desktop(*args: Any, **kwargs: Any):
    """Has desktop check — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.frameworks.desktop_launch.agent_has_desktop`。
    """
    from lib.adapters.frameworks.desktop_launch import agent_has_desktop as _impl

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


def merge_launch_desktop(*args: Any, **kwargs: Any) -> Any:
    from lib.adapters.frameworks.desktop_launch import merge_launch_desktop as _fn

    return _fn(*args, **kwargs)


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


def openclaw_adapter_class():
    """OpenClawAdapter class — api/handlers_system 通过本函数拿到 adapter 类。

    实际实现见 `lib.adapters.frameworks.OpenClawAdapter`。
    """
    from lib.adapters.frameworks import OpenClawAdapter as _impl

    return _impl


__all__ = [
    "try_build_push_direct",
    "parse_model_from_push_template",
    "type_supports_auto_ack",
    "store_path_for_agent",
    "agent_cli_active",
    "agent_cli_active_for",
    "framework_push_template",
    "get_framework_spec",
    "list_framework_types",
    "resolve_push_cli",
    "should_mark_processing_on_push",
    "push_timeout_for",
    "launch_queue_prefix",
    "enqueue_launch_queue",
    "ensure_framework_plugins_loaded",
    "clear_framework_discovery_cache",
    "framework_run_targets",
    "framework_status",
    "scan_framework_agents",
    "resolve_browser_url",
    "agent_has_desktop",
    "launch_desktop",
    "launch_claude_browser",
    "launch_claude_cli",
    "merge_launch_desktop",
    "reload_framework_plugins",
    "resolve_container",
    "framework_get_adapter",
    "supports_interactive_cli",
    "build_interactive_cli_command",
    "openclaw_adapter_class",
]
