"""Agent launch 端口默认值与解析 — 默认表 + transport/store 自定义覆盖。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .constants import MAILBUS_ROOT

PORT_KEYS = ("dashboard_port", "web_port", "gateway_port", "port")

PORT_KEY_BY_TYPE: dict[str, str] = {
    "hermes_profile": "dashboard_port",
    "codex": "web_port",
    "claude_code": "web_port",
    "openclaw": "gateway_port",
}


@lru_cache(maxsize=1)
def load_launch_port_defaults() -> dict[str, Any]:
    path = MAILBUS_ROOT / "config" / "mailbus" / "launch-ports.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if not str(k).startswith("_")}


def _infer_port_group(agent_cfg: dict, browser_cfg: dict | None = None) -> str:
    browser_cfg = browser_cfg or {}
    kind = (browser_cfg.get("kind") or "").strip()
    if kind in ("codex_desktop", "codex_web", "codex_ui", "codex_docker"):
        return "codex_web"
    if kind in ("claude_ttyd", "claude_web"):
        return "claude_browser"
    if kind == "openclaw_gateway":
        return "openclaw_gateway"
    if kind == "hermes_dashboard":
        return "hermes_dashboard"
    agent_type = (agent_cfg.get("type") or "").strip()
    if agent_type == "codex":
        return "codex_web"
    if agent_type == "claude_code":
        return "claude_browser"
    if agent_type == "openclaw":
        return "openclaw_gateway"
    if agent_type == "hermes_profile":
        return "hermes_dashboard"
    return ""


def default_port(agent_key: str, *, group: str) -> int | None:
    table = load_launch_port_defaults().get(group) or {}
    raw = table.get(agent_key)
    if raw not in (None, ""):
        return int(raw)
    fallback = table.get("_fallback")
    if fallback not in (None, ""):
        return int(fallback)
    return None


def resolve_port(
    agent_key: str,
    agent_cfg: dict,
    browser_cfg: dict | None = None,
    *,
    group: str = "",
) -> int | None:
    """解析端口：launch.browser 自定义 > docker.port > launch-ports.json 默认。"""
    browser_cfg = browser_cfg or {}
    for key in PORT_KEYS:
        raw = browser_cfg.get(key)
        if raw not in (None, ""):
            return int(raw)
    docker_port = (agent_cfg.get("docker") or {}).get("port")
    if docker_port not in (None, ""):
        return int(docker_port)
    group = group or _infer_port_group(agent_cfg, browser_cfg)
    if not group:
        return None
    return default_port(agent_key, group=group)


def resolve_codex_ttyd_port(agent_key: str, browser_cfg: dict | None = None) -> int | None:
    browser_cfg = browser_cfg or {}
    raw = browser_cfg.get("ttyd_port")
    if raw not in (None, ""):
        return int(raw)
    ttyd_url = (browser_cfg.get("ttyd_url") or "").strip()
    if ttyd_url:
        import re

        m = re.search(r":(\d+)/?", ttyd_url)
        if m:
            return int(m.group(1))
    return default_port(agent_key, group="codex_ttyd")


def build_browser_url(
    agent_key: str,
    agent_cfg: dict,
    browser_cfg: dict,
    *,
    default_path: str = "/chat",
) -> str:
    """根据模板 url + 解析端口生成浏览器 URL。"""
    url = (browser_cfg.get("url") or "").strip()
    port = resolve_port(agent_key, agent_cfg, browser_cfg)
    if url and port is not None:
        url = url.replace("{port}", str(port)).replace("{agent}", agent_key)
        return url
    if port is not None:
        return f"http://127.0.0.1:{port}{default_path}"
    return url.replace("{agent}", agent_key) if url else ""


def port_config_key(agent_cfg: dict, browser_cfg: dict | None = None) -> str:
    browser_cfg = browser_cfg or {}
    kind = (browser_cfg.get("kind") or "").strip()
    if kind == "hermes_dashboard":
        return "dashboard_port"
    if kind in ("codex_desktop", "codex_web", "codex_ui", "codex_docker"):
        return "web_port"
    if kind == "openclaw_gateway":
        return "gateway_port"
    if kind in ("claude_ttyd", "claude_web"):
        return "web_port"
    return PORT_KEY_BY_TYPE.get((agent_cfg.get("type") or "").strip(), "port")


def merged_browser_cfg(
    agent_cfg: dict,
    agent_types: dict,
) -> dict:
    launch = agent_cfg.get("launch") or {}
    tmpl_name = launch.get("template", "")
    tmpl = (agent_types.get("launch_templates") or {}).get(tmpl_name, {})
    merged = dict(tmpl.get("browser") or {})
    merged.update(launch.get("browser") or {})
    return merged


def collect_launch_port_items(
    agents: dict[str, dict],
    agent_types: dict,
) -> list[dict[str, Any]]:
    """Dashboard launch_ports 段：每 agent 当前端口、默认值、配置键。"""
    items: list[dict[str, Any]] = []
    for agent_id in sorted(agents):
        agent_cfg = agents[agent_id] or {}
        launch = agent_cfg.get("launch") or {}
        if not launch.get("has_browser", True):
            continue
        browser = merged_browser_cfg(agent_cfg, agent_types)
        audit = audit_agent_port(agent_id, agent_cfg, browser)
        group = audit.get("group") or ""
        port_key = port_config_key(agent_cfg, browser)
        default = default_port(agent_id, group=group) if group else None
        entry: dict[str, Any] = {
            "id": agent_id,
            "name": agent_cfg.get("name", agent_id),
            "type": agent_cfg.get("type", ""),
            "port": audit.get("port"),
            "default_port": default,
            "port_key": port_key,
            "port_label": {
                "dashboard_port": "Dashboard 端口",
                "web_port": "Web UI 端口",
                "gateway_port": "Gateway 端口",
                "port": "端口",
            }.get(port_key, "端口"),
            "source": audit.get("source", ""),
            "group": group,
            "launch_url": build_browser_url(agent_id, agent_cfg, browser),
        }
        if agent_cfg.get("type") == "codex":
            ttyd = resolve_codex_ttyd_port(agent_id, browser)
            entry["ttyd_port"] = ttyd
            entry["default_ttyd_port"] = default_port(agent_id, group="codex_ttyd")
        items.append(entry)
    return items


def apply_launch_port_patch(
    cfg: dict,
    agent_id: str,
    *,
    port: int | None = None,
    ttyd_port: int | None = None,
    reset: bool = False,
) -> None:
    """写入 store/config.json — agents.<id>.launch.browser 端口覆盖。"""
    agents = cfg.get("agents") or {}
    if agent_id not in agents:
        raise ValueError(f"unknown agent: {agent_id}")
    agent_cfg = agents[agent_id]
    agent_types = cfg.get("agent_types") or {}
    browser = merged_browser_cfg(agent_cfg, agent_types)
    port_key = port_config_key(agent_cfg, browser)
    launch = agent_cfg.setdefault("launch", {})
    browser_cfg = launch.setdefault("browser", {})

    if reset:
        browser_cfg.pop(port_key, None)
        if agent_cfg.get("type") == "codex":
            browser_cfg.pop("ttyd_url", None)
            browser_cfg.pop("ttyd_port", None)
        if agent_cfg.get("type") == "claude_code":
            mc = cfg.get("mailbus_claude") or {}
            for plat in (mc.get("platforms") or {}).values():
                if isinstance(plat, dict) and isinstance(plat.get("browser_ports"), dict):
                    plat["browser_ports"].pop(agent_id, None)
    else:
        if port is not None:
            browser_cfg[port_key] = int(port)
        if ttyd_port is not None and agent_cfg.get("type") == "codex":
            browser_cfg["ttyd_url"] = f"http://127.0.0.1:{int(ttyd_port)}/"

    if agent_cfg.get("type") == "claude_code" and port is not None:
        mc = cfg.setdefault("mailbus_claude", {})
        platforms = mc.setdefault("platforms", {})
        for plat_name in ("windows", "linux"):
            plat = platforms.setdefault(plat_name, {})
            ports = plat.setdefault("browser_ports", {})
            ports[agent_id] = int(port)


def audit_agent_port(
    agent_key: str,
    agent_cfg: dict,
    browser_cfg: dict,
) -> dict[str, Any]:
    """返回审计条目：解析端口、来源、默认组。"""
    group = _infer_port_group(agent_cfg, browser_cfg)
    port = resolve_port(agent_key, agent_cfg, browser_cfg, group=group)
    source = "default"
    for key in PORT_KEYS:
        if browser_cfg.get(key) not in (None, ""):
            source = f"launch.browser.{key}"
            break
    else:
        if (agent_cfg.get("docker") or {}).get("port") not in (None, ""):
            source = "docker.port"
    return {
        "agent": agent_key,
        "type": agent_cfg.get("type", ""),
        "group": group,
        "port": port,
        "source": source,
        "url_template": browser_cfg.get("url", ""),
    }
