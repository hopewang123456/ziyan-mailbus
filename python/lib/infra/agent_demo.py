"""Agent demo roster 读取 — 主代码不硬编码实例/角色 id。

主代码中所有和实例、角色相关的核心信息统一从配置读取。当 store/team-pack
未提供真实花名册时，回落到 ``config/mailbus/agent-demo.json`` 的公开 demo
名单（通用 agent id），保证开源克隆后开箱可跑。禁止在本模块之外硬编码
个人名册或本地路径。

运行时优先级：
  1. 各模块自身的 store/config.json 配置（真实花名册）
  2. ``config/mailbus/agent-demo.json`` demo seed
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from lib.infra.constants import MAILBUS_ROOT
from lib.infra.utils import json_read

_DEMO_PATH = os.path.join(str(MAILBUS_ROOT), "config", "mailbus", "agent-demo.json")


@lru_cache(maxsize=1)
def _load_demo() -> dict:
    doc = json_read(_DEMO_PATH, {})
    return doc if isinstance(doc, dict) else {}


def _section(key: str) -> dict:
    section = _load_demo().get(key) or {}
    return section if isinstance(section, dict) else {}


def hermes_demo_agents() -> list[str]:
    return [str(x) for x in (_section("hermes").get("demo_agents") or []) if str(x).strip()]


def first_demo_agent() -> str:
    """返回 demo 名单第一个 agent id（兜底用，避免主代码硬编码）。"""
    agents = hermes_demo_agents()
    return agents[0] if agents else ""


def hermes_demo_dashboards() -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for item in _section("hermes").get("demo_dashboards") or []:
        if isinstance(item, dict) and item.get("agent") and item.get("port") is not None:
            out.append((str(item["agent"]), int(item["port"])))
    return out


def openclaw_state_dirs() -> dict[str, str]:
    return {str(k): str(v) for k, v in (_section("openclaw").get("state_dirs") or {}).items()}


def openclaw_gateway_ports() -> dict[str, int]:
    return {str(k): int(v) for k, v in (_section("openclaw").get("gateway_ports") or {}).items()}


def codex_agent_display() -> dict[str, str]:
    return {str(k): str(v) for k, v in (_section("codex").get("agent_display") or {}).items()}


def codex_default_models() -> dict[str, tuple]:
    return {
        str(k): tuple(v) if isinstance(v, list) else v
        for k, v in (_section("codex").get("default_models") or {}).items()
    }


def pipeline_legacy_agent_role() -> dict[str, str]:
    return {str(k): str(v) for k, v in (_section("pipeline").get("legacy_agent_role") or {}).items()}


def pipeline_full_agents() -> list[str]:
    return [str(x) for x in (_section("pipeline").get("full_pipeline_agents") or []) if str(x).strip()]


def pipeline_role_flow() -> dict[str, str]:
    """role_flow demo fallback（'角色|结论' → 下一角色 或 '' 表示终止）。"""
    return {str(k): str(v) for k, v in (_section("pipeline").get("role_flow") or {}).items()}


def bulletin_default_posters() -> list[str]:
    return [str(x) for x in (_section("bulletin").get("default_posters") or []) if str(x).strip()]


def bulletin_default_list() -> list[str]:
    return [str(x) for x in (_section("bulletin").get("default_bulletin") or []) if str(x).strip()]


def clinic_demo_agents() -> list[str]:
    return [str(x) for x in (_section("clinic").get("demo_agents") or []) if str(x).strip()]


def org_demo_defaults() -> dict[str, Any]:
    """org_defaults demo fallback（agent-demo.json → org_defaults 段）。"""
    return {str(k): v for k, v in (_section("org_defaults") or {}).items()}


def validate_agent_demo() -> list[str]:
    """校验 agent-demo.json 结构；返回错误列表（空 = 通过）。"""
    import re

    errors: list[str] = []
    doc = _load_demo()
    if not doc:
        errors.append("agent-demo.json missing or empty")
        return errors
    if not isinstance(doc.get("version"), str):
        errors.append("missing version")
    agent_id_re = re.compile(r"^agent-[a-z0-9]+$")
    for label, agents in (
        ("hermes.demo_agents", hermes_demo_agents()),
        ("bulletin.default_posters", bulletin_default_posters()),
        ("bulletin.default_bulletin", bulletin_default_list()),
        ("pipeline.full_pipeline_agents", pipeline_full_agents()),
    ):
        for aid in agents:
            if not agent_id_re.match(aid):
                errors.append(f"{label}: invalid agent id {aid!r}")
    for key in (openclaw_state_dirs() or {}):
        if not agent_id_re.match(key):
            errors.append(f"openclaw.state_dirs: invalid agent id {key!r}")
    for key, port in (openclaw_gateway_ports() or {}).items():
        if not agent_id_re.match(key):
            errors.append(f"openclaw.gateway_ports: invalid agent id {key!r}")
        if not isinstance(port, int) or not (0 < port < 65536):
            errors.append(f"openclaw.gateway_ports[{key}]: invalid port {port!r}")
    for key in (codex_agent_display() or {}):
        if not agent_id_re.match(key):
            errors.append(f"codex.agent_display: invalid agent id {key!r}")
    return errors


def clear_agent_demo_cache() -> None:
    _load_demo.cache_clear()


def reload() -> None:
    clear_agent_demo_cache()
    _load_demo()


__all__ = [
    "hermes_demo_agents",
    "first_demo_agent",
    "hermes_demo_dashboards",
    "openclaw_state_dirs",
    "openclaw_gateway_ports",
    "codex_agent_display",
    "codex_default_models",
    "pipeline_legacy_agent_role",
    "pipeline_full_agents",
    "pipeline_role_flow",
    "bulletin_default_posters",
    "bulletin_default_list",
    "clinic_demo_agents",
    "org_demo_defaults",
    "validate_agent_demo",
    "clear_agent_demo_cache",
    "reload",
]
