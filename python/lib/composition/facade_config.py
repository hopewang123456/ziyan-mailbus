"""Composition facades — config / integrations domain (R2 split from composition.py).

Target domain: adapters.config.* and adapters.integrations.*
(settings / registry / compose files / browser auth / avatars / plugin loading).
"""
from __future__ import annotations

from typing import Any


def run_init_store(data_dir: str, *, fresh: bool = False) -> int:
    from lib.adapters.config.init_store import run_init_store as _run

    return _run(data_dir, fresh=fresh)


def run_merge_store_config(data_dir: str, *, quiet: bool = False) -> int:
    from lib.adapters.config.init_store import run_merge_store_config as _run

    return _run(data_dir, quiet=quiet)


def validate_config(config: dict) -> list[str]:
    from lib.adapters.config.config_schema import validate_config as _validate

    return _validate(config)


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


def assembly_card(*args: Any, **kwargs: Any):
    """E5 装配结果卡片 — api/application 经此访问（分层约束）。

    实际实现见 `lib.adapters.config.assembly_card.assembly_card`。
    """
    from lib.adapters.config.assembly_card import assembly_card as _impl

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


def config_path(*args: Any, **kwargs: Any):
    """Config path — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.config_admin.config_path`。
    """
    from lib.adapters.config.config_admin import config_path as _impl

    return _impl(*args, **kwargs)


def ensure_integration_plugins_loaded(*args: Any, **kwargs: Any):
    """Integration 插件加载 — api 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.integrations.entry_point_discovery.ensure_integration_plugins_loaded`。
    """
    from lib.adapters.integrations.entry_point_discovery import (
        ensure_integration_plugins_loaded as _impl,
    )

    return _impl(*args, **kwargs)


def reload_integration_plugins(*args: Any, **kwargs: Any):
    """Reload integration plugins — api/handlers_settings 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.integrations.entry_point_discovery.reload_integration_plugins`。
    """
    from lib.adapters.integrations.entry_point_discovery import (
        reload_integration_plugins as _impl,
    )

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


def redact_api_token(*args: Any, **kwargs: Any):
    """API token redact — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.config_admin._redact_api_token`。
    """
    from lib.adapters.config.config_admin import _redact_api_token as _impl

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


def openclaw_gateway_token(*args: Any, **kwargs: Any):
    """OpenClaw gateway token — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.browser_auth.openclaw_gateway_token`。
    """
    from lib.adapters.config.browser_auth import openclaw_gateway_token as _impl

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


def resolve_port(*args: Any, **kwargs: Any):
    """launch port 解析 — api/handlers_system 通过本函数拿到 adapter 服务。

    实际实现见 `lib.adapters.config.launch_ports.resolve_port`。
    """
    from lib.adapters.config.launch_ports import resolve_port as _impl

    return _impl(*args, **kwargs)


def get_agent_profile(*args: Any, **kwargs: Any) -> Any:
    from lib.adapters.config.profile_registry import get_profile

    return get_profile(*args, **kwargs)


def resolve_config_path(*args: Any, **kwargs: Any) -> Any:
    from lib.adapters.config.config_files import resolve_config_path as _fn

    return _fn(*args, **kwargs)


def warn_if_config_missing(*args: Any, **kwargs: Any) -> None:
    from lib.adapters.config.config_files import warn_if_missing as _fn

    _fn(*args, **kwargs)


__all__ = [
    "run_init_store",
    "run_merge_store_config",
    "validate_config",
    "memory_bridge_module",
    "load_roles_for_instance",
    "upsert_instance",
    "discover_roles_for_instance",
    "scan_agent_assets",
    "assembly_card",
    "config_env_status",
    "config_get_section",
    "config_list_sections",
    "config_patch_env",
    "config_patch_section",
    "list_compose_files",
    "read_compose_file",
    "write_compose_file",
    "build_skills_index_from_registry",
    "config_mailbus_root",
    "config_path",
    "ensure_integration_plugins_loaded",
    "reload_integration_plugins",
    "effective_scan_interval_seconds",
    "measure_mailbus_activity",
    "get_agent",
    "mailbus_root_sys",
    "redact_api_token",
    "build_authed_url",
    "resolve_agent_auth",
    "openclaw_gateway_token",
    "resolve_avatar_urls",
    "resolve_animated_file",
    "resolve_portrait_file",
    "resolve_port",
    "get_agent_profile",
    "resolve_config_path",
    "warn_if_config_missing",
]
