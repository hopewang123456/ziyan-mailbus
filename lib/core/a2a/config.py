"""Transport 配置加载。"""
from __future__ import annotations

import os
from typing import Any, Optional

from lib.infra.constants import MAILBUS_ROOT
from lib.infra.utils import json_read

_DEFAULT = {
    "channel_order": ["a2a_standard", "file_bus"],
    "a2a": {
        "max_retries": 3,
        "retry_backoff_sec": [2, 5, 10],
        "poll_interval_sec": [2, 5],
        "input_required_timeout_sec": 86400,
        "stream_poll_sec": 0.1,
        "stream_timeout_sec": 120,
        "stream_heartbeat_sec": 15,
        "stream_max_events": 0,
        "stream_missing_grace_sec": 0.3,
        "use_streaming": False,
    },
    "file_bus": {"enabled": True},
    "fallback_alerts": {"enabled": True, "notify_agent": "agent-a"},
}


def _deep_merge(dst: dict, src: dict) -> dict:
    for key, val in (src or {}).items():
        if key in dst and isinstance(dst[key], dict) and isinstance(val, dict):
            _deep_merge(dst[key], val)
        else:
            dst[key] = val
    return dst


def _transport_blob(raw: dict) -> dict:
    """与 init_store.load_config_fragments 一致：优先嵌套 transport.*。"""
    if not raw:
        return {}
    return raw.get("transport") or raw


def _default_transport() -> dict[str, Any]:
    return {
        "channel_order": list(_DEFAULT["channel_order"]),
        "a2a": dict(_DEFAULT["a2a"]),
        "file_bus": dict(_DEFAULT["file_bus"]),
        "fallback_alerts": dict(_DEFAULT["fallback_alerts"]),
    }


def load_transport_config(config: Optional[dict] = None, data_dir: str = "") -> dict[str, Any]:
    merged = _default_transport()
    tpl = MAILBUS_ROOT / "config" / "mailbus" / "transport.template.json"
    if tpl.is_file():
        _deep_merge(merged, _transport_blob(json_read(str(tpl), {})))
    if data_dir:
        store_cfg = json_read(os.path.join(data_dir, "config.json"), {})
        _deep_merge(merged, store_cfg.get("transport") or {})
    if config:
        _deep_merge(merged, config.get("transport") or {})
    return merged


def resolve_use_streaming(config: Optional[dict] = None, agent_cfg: Optional[dict] = None) -> bool:
    """解析是否启用 A2A streaming：agent channels.a2a.use_streaming 优先于全局。"""
    if agent_cfg:
        a2a_ch = ((agent_cfg.get("channels") or {}).get("a2a") or {})
        if "use_streaming" in a2a_ch:
            return bool(a2a_ch["use_streaming"])
    cfg = config or {}
    a2a_cfg = (cfg.get("transport") or {}).get("a2a") or cfg.get("a2a") or {}
    return bool(a2a_cfg.get("use_streaming"))
