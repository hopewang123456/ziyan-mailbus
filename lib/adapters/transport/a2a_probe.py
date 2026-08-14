"""A2A endpoint 可用性探测 — 保存 Agent 时写入 channels.a2a.available。"""
from __future__ import annotations

from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from lib.infra.utils import _now_iso


def resolve_a2a_rpc_url(agent_cfg: dict) -> str:
    """复用 HttpA2AClient.from_agent_config 的 endpoint 解析规则。"""
    endpoint = (agent_cfg or {}).get("endpoint") or {}
    card = (agent_cfg or {}).get("agent_card") or (agent_cfg or {}).get("wire") or {}
    interfaces = card.get("supportedInterfaces") or (agent_cfg or {}).get("supportedInterfaces") or []
    rpc_url = endpoint.get("rpc_url") or endpoint.get("base_url") or ""
    if not rpc_url and interfaces:
        rpc_url = (interfaces[0] or {}).get("url") or ""
    return (rpc_url or "").strip()


def probe_a2a_availability(agent_cfg: dict, timeout: float = 5.0) -> dict[str, Any]:
    """轻量探测 A2A endpoint 是否可达（GET，无副作用）。

    返回 {available: bool, rpc_url: str, detail: str}。仅判断配置是否声明 + 端点存活，
    不发送真实任务；`channels.a2a.enabled=False` 或 `transport=local_cli` 时直接不可用。
    """
    if (agent_cfg or {}).get("transport") == "local_cli":
        return {"available": False, "rpc_url": "", "detail": "local_cli"}
    channels = (agent_cfg or {}).get("channels") or {}
    a2a_ch = channels.get("a2a") or {}
    if a2a_ch.get("enabled") is False:
        return {"available": False, "rpc_url": "", "detail": "disabled"}

    rpc_url = resolve_a2a_rpc_url(agent_cfg)
    if not rpc_url:
        return {"available": False, "rpc_url": "", "detail": "no_endpoint"}

    try:
        req = urlrequest.Request(rpc_url, method="GET")
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            return {"available": True, "rpc_url": rpc_url, "detail": f"http {resp.status}"}
    except urlerror.HTTPError as exc:
        # 4xx/5xx 说明端点存在（路由可达），只是 GET 不被允许
        return {"available": True, "rpc_url": rpc_url, "detail": f"http {exc.code}"}
    except (urlerror.URLError, TimeoutError, OSError) as exc:
        return {"available": False, "rpc_url": rpc_url, "detail": str(exc)}


def stamp_a2a_probe(agent_cfg: dict, timeout: float = 5.0) -> dict[str, Any]:
    """探测并写回 channels.a2a.{available,rpc_url,probed_at}，返回更新后的 agent_cfg。"""
    probe = probe_a2a_availability(agent_cfg, timeout=timeout)
    channels = agent_cfg.setdefault("channels", {})
    a2a_ch = dict(channels.get("a2a") or {})
    a2a_ch["available"] = bool(probe.get("available"))
    a2a_ch["rpc_url"] = probe.get("rpc_url") or ""
    a2a_ch["probed_at"] = _now_iso()
    channels["a2a"] = a2a_ch
    return agent_cfg
