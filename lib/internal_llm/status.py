"""Internal LLM 状态摘要。"""

from __future__ import annotations

import os

from ..utils import json_read
from .budget import _load
from .planner_llm import load_llm_config
from .rag.index import index_info


def llm_status(data_dir: str) -> dict:
    cfg = load_llm_config(data_dir)
    budget = _load(data_dir)
    rag = index_info(data_dir, cfg) if cfg.get("rag", {}).get("enabled", True) else {}
    providers = cfg.get("providers") or {}
    active = None
    for name in cfg.get("provider_priority") or []:
        if name in providers:
            active = name
            break
    return {
        "enabled": bool(cfg.get("enabled")),
        "active_provider": active,
        "provider_priority": cfg.get("provider_priority") or ["local", "remote"],
        "providers": list(providers.keys()),
        "provider_endpoints": {
            name: {
                "kind": (providers.get(name) or {}).get("kind"),
                "base_url": (providers.get(name) or {}).get("base_url"),
                "model": (providers.get(name) or {}).get("model"),
            }
            for name in (cfg.get("provider_priority") or [])
            if name in providers
        },
        "fallback_mode": "local_first",
        "triggers": cfg.get("triggers") or {},
        "guardrails": cfg.get("guardrails") or {},
        "budget": {
            "hour": budget.get("hour"),
            "calls_this_hour": budget.get("calls", 0),
            **(cfg.get("budget") or {}),
        },
        "rag": rag,
    }
