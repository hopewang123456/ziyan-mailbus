"""Internal LLM 配置解析（env 占位符等）。"""

from __future__ import annotations

import os
from copy import deepcopy


def resolve_llm_config(raw: dict) -> dict:
    cfg = deepcopy(raw or {})
    providers = cfg.get("providers") or {}
    for name, pc in list(providers.items()):
        if not isinstance(pc, dict):
            continue
        env_key = pc.get("api_key_env")
        if env_key and not pc.get("api_key"):
            val = os.environ.get(env_key)
            if val:
                pc = dict(pc)
                pc["api_key"] = val
                providers[name] = pc
    cfg["providers"] = providers
    return cfg
