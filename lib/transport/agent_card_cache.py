"""Agent Card 缓存 — store/agents/cards + registry 合成。"""
from __future__ import annotations

from lib.adapters.clock import now_dt, now_ts, now_utc_dt
import json
import os
import time
from typing import Any, Optional

from ..constants import MAILBUS_ROOT, TEAM_PACK_ROOT
from ..utils import json_read
from .a2a_mapper import to_agent_card

_TTL_SEC = 300
_cache: dict[str, tuple[float, dict]] = {}


def _registry_path(data_dir: str = "") -> str:
    for base in (
        os.path.join(data_dir, "roles", "json", "agent-registry.json") if data_dir else "",
        str(TEAM_PACK_ROOT / "org" / "json" / "agent-registry.json"),
        str(MAILBUS_ROOT / "store" / "roles" / "json" / "agent-registry.json"),
    ):
        if base and os.path.isfile(base):
            return base
    return str(TEAM_PACK_ROOT / "org" / "json" / "agent-registry.json")


def _channels_path() -> str:
    return str(MAILBUS_ROOT / "config" / "mailbus" / "agent-channels.json")


def load_registry(data_dir: str = "") -> dict[str, Any]:
    path = _registry_path(data_dir)
    doc = json_read(path, {})
    return doc.get("agents") or doc


def _merge_channel_defaults(defaults: dict, existing: dict) -> dict:
    out = dict(defaults or {})
    for name, cfg in (existing or {}).items():
        if name in out and isinstance(out[name], dict) and isinstance(cfg, dict):
            out[name] = {**out[name], **cfg}
        else:
            out[name] = cfg
    return out


def enrich_agent_channels(agent_id: str, entry: dict) -> dict:
    """合并 agent-channels.json defaults（channels 深合并，保留 per-agent use_streaming 等）。"""
    merged = dict(entry)
    ch_doc = json_read(_channels_path(), {})
    defaults = (ch_doc.get("defaults") or {}).get(merged.get("runtime") or merged.get("framework") or "") or {}
    if defaults.get("channels"):
        merged["channels"] = _merge_channel_defaults(defaults["channels"], merged.get("channels") or {})
    if defaults.get("endpoint") and not merged.get("endpoint"):
        ep = dict(defaults["endpoint"])
        if "{agent_id}" in str(ep.get("base_url", "")):
            ep["base_url"] = ep["base_url"].replace("{agent_id}", agent_id)
        merged["endpoint"] = ep
    if defaults.get("transport") and not merged.get("transport"):
        merged["transport"] = defaults["transport"]
    fg_map = ch_doc.get("functional_group") or {}
    merged.setdefault("functional_group", fg_map.get(agent_id, ""))
    return merged


def card_store_path(data_dir: str, agent_id: str) -> str:
    return os.path.join(data_dir, "agents", "cards", f"{agent_id}.json")


class AgentCardCache:
    def __init__(self, *, data_dir: str = "", base_url: str = "https://mailbus.example"):
        self.data_dir = data_dir
        self.base_url = base_url

    def get(self, agent_id: str, *, force_refresh: bool = False) -> Optional[dict]:
        now = now_ts()
        if not force_refresh and agent_id in _cache:
            ts, card = _cache[agent_id]
            if now - ts < _TTL_SEC:
                return card

        store_path = card_store_path(self.data_dir, agent_id) if self.data_dir else ""
        if store_path and os.path.isfile(store_path):
            doc = json_read(store_path, {})
            wire = doc.get("wire") or doc
            _cache[agent_id] = (now, wire)
            return wire

        registry = load_registry(self.data_dir)
        entry = registry.get(agent_id)
        if not entry:
            return None
        entry = enrich_agent_channels(agent_id, entry)
        from ..profile_registry import get_profile

        prof = get_profile(agent_id) or {}
        display = prof.get("display_name") or entry.get("display_name") or agent_id
        card = to_agent_card(
            agent_id, entry,
            display_name=display,
            functional_group=entry.get("functional_group", ""),
            base_url=self.base_url,
        )
        _cache[agent_id] = (now, card)
        return card

    def invalidate(self, agent_id: str) -> None:
        _cache.pop(agent_id, None)
