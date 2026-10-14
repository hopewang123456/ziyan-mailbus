"""Work-order chain routing: human templates + Ollama first, else LLM generate."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from lib.composition import build_orchestration
from lib.infra.utils import json_read, json_write

DEFAULT_DAILY_BUDGET_CNY = 30.0


def load_chain_templates(cfg: dict) -> list[dict]:
    return list((cfg.get("mailbus_chains") or {}).get("templates") or [])


def pick_template(cfg: dict, *, role_type: Any = None, tags: list[str] | None = None) -> dict | None:
    tags = tags or []
    for t in load_chain_templates(cfg):
        if role_type is not None and t.get("role_type") not in (None, role_type):
            continue
        t_tags = set(t.get("tags") or [])
        if tags and t_tags and not t_tags.intersection(tags):
            continue
        return t
    # first default
    for t in load_chain_templates(cfg):
        if t.get("default"):
            return t
    return None


def list_ollama_models(base_url: str = "") -> list[str]:
    base = (base_url or os.environ.get("MAILBUS_OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m.get("name") for m in (data.get("models") or []) if m.get("name")]
    except Exception:
        return []


def resolve_ollama_model(cfg: dict) -> str | None:
    llm = cfg.get("mailbus_internal_llm") or {}
    ollama = llm.get("ollama") or {}
    local = (llm.get("providers") or {}).get("local") or {}
    svc = (cfg.get("services") or {}).get("ollama") or {}
    base_url = (
        ollama.get("base_url")
        or local.get("base_url")
        or svc.get("base_url")
        or os.environ.get("MAILBUS_OLLAMA_BASE_URL")
        or ""
    )
    configured = (
        ollama.get("default_model")
        or ollama.get("model")
        or local.get("model")
        or svc.get("model")
        or os.environ.get("MAILBUS_OLLAMA_MODEL")
        or ""
    ).strip()
    models = list_ollama_models(base_url)
    if configured and (not models or configured in models or any(configured.split(":")[0] in m for m in models)):
        return configured
    if models:
        return models[0]
    return configured or None


def ensure_llm_or_prompt(cfg: dict) -> dict[str, Any]:
    """Return {ok, model, provider, prompt_user}."""
    model = resolve_ollama_model(cfg)
    if model:
        return {"ok": True, "provider": "ollama", "model": model, "prompt_user": False}
    # cloud key present?
    if os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("MAILBUS_INTERNAL_LLM_API_KEY"):
        return {"ok": True, "provider": "remote", "model": "remote-default", "prompt_user": False}
    return {
        "ok": False,
        "provider": None,
        "model": None,
        "prompt_user": True,
        "message": "No Ollama models and no LLM API key. Configure Ollama or an API key in Settings.",
    }


def budget_state_path(data_dir: str) -> str:
    return os.path.join(data_dir, "system", "chain-budget.json")


def load_budget(data_dir: str, cfg: dict) -> dict:
    return build_orchestration(data_dir).budget.load(cfg)


def record_chain_spend(data_dir: str, cfg: dict, amount_cny: float) -> dict:
    """Orchestration spend — delegates to BudgetMeter + Notifier (Wave2)."""
    from lib.application.orchestration.mediator import record_spend

    return record_spend(data_dir, amount_cny, cfg)


def apply_ollama_decision(data_dir: str, cfg: dict, *, use_ollama: bool | None) -> dict:
    """Q8B: budget FSM decision + pause/resume task FSM."""
    from lib.application.orchestration.mediator import apply_budget_decision

    return apply_budget_decision(data_dir, use_ollama, cfg)


def instantiate_chain(
    data_dir: str,
    cfg: dict,
    *,
    task_id: str,
    role_type: Any = None,
    tags: list[str] | None = None,
    steps_override: list[dict] | None = None,
) -> dict[str, Any]:
    llm = ensure_llm_or_prompt(cfg)
    if not llm.get("ok"):
        return {"ok": False, "error": llm.get("message"), "prompt_user": True}

    budget = load_budget(data_dir, cfg)
    if budget.get("paused") or budget.get("fsm_state") == "paused_budget":
        return {"ok": False, "error": "chain routing paused (budget)", "paused": True, "error_code": "budget_paused"}

    tmpl = pick_template(cfg, role_type=role_type, tags=tags)
    steps = steps_override
    source = "template+ollama"
    if not steps:
        if tmpl:
            steps = list(tmpl.get("steps") or [])
        else:
            # LLM auto-generate placeholder chain (real LLM call can plug in later)
            steps = [
                {"agent_role": "dispatcher", "action": "plan"},
                {"agent_role": "executor", "action": "implement"},
                {"agent_role": "reviewer", "action": "review"},
            ]
            source = "llm_generated"

    chain = {
        "task_id": task_id,
        "source": source,
        "model": llm.get("model"),
        "provider": llm.get("provider"),
        "steps": steps,
        "cursor": 0,
    }
    path = os.path.join(data_dir, "system", "chains", f"{task_id}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json_write(path, chain)
    return {"ok": True, "chain": chain, "path": path}


__all__ = [
    "DEFAULT_DAILY_BUDGET_CNY",
    "apply_ollama_decision",
    "budget_state_path",
    "ensure_llm_or_prompt",
    "instantiate_chain",
    "list_ollama_models",
    "load_budget",
    "load_chain_templates",
    "pick_template",
    "record_chain_spend",
    "resolve_ollama_model",
]
