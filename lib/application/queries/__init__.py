"""Read-side queries (CQRS-lite)."""
from __future__ import annotations

from typing import Any

from lib.application.lifecycle import list_active_agents
from lib.utils import json_read


def active_agents(data_dir: str) -> dict[str, dict]:
    cfg = json_read(f"{data_dir}/config.json", {})
    return list_active_agents(cfg)


def chain_budget_view(data_dir: str) -> dict[str, Any]:
    from lib.application.chain_route import ensure_llm_or_prompt, load_budget

    cfg = json_read(f"{data_dir}/config.json", {})
    return {"budget": load_budget(data_dir, cfg), "llm": ensure_llm_or_prompt(cfg)}
