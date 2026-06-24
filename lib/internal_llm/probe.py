"""Internal LLM provider 健康探测（Ollama 仅走官方 /api/tags）。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List

from .planner_llm import load_llm_config


def _probe_ollama(pc: dict) -> dict:
    base = (pc.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
    model = pc.get("model") or ""
    timeout = int(pc.get("timeout_seconds") or 10)
    try:
        req = urllib.request.Request(f"{base}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        models = [m.get("name") for m in (data.get("models") or []) if m.get("name")]
        has_model = (not model) or any(model in m or m.startswith(model + ":") for m in models)
        return {
            "ok": True,
            "kind": "ollama",
            "base_url": base,
            "model": model,
            "model_available": has_model,
            "models_count": len(models),
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {"ok": False, "kind": "ollama", "base_url": base, "error": str(exc)}


def _probe_openai_compatible(name: str, pc: dict) -> dict:
    base = (pc.get("base_url") or "").rstrip("/")
    env_key = pc.get("api_key_env") or "MAILBUS_INTERNAL_LLM_API_KEY"
    api_key = os.environ.get(env_key) or pc.get("api_key") or ""
    if not base:
        return {"ok": False, "kind": "openai_compatible", "error": "missing base_url"}
    if not api_key:
        return {"ok": False, "kind": "openai_compatible", "base_url": base, "error": f"missing env {env_key}"}
    timeout = int(pc.get("timeout_seconds") or 10)
    try:
        req = urllib.request.Request(
            f"{base}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        models = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        model = pc.get("model") or ""
        has_model = (not model) or any(model in m or m.startswith(model + ":") for m in models)
        return {
            "ok": True,
            "kind": "openai_compatible",
            "base_url": base,
            "model": model,
            "model_available": has_model,
            "models_count": len(models),
        }
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {"ok": False, "kind": "openai_compatible", "base_url": base, "error": f"auth failed ({exc.code})"}
        return {
            "ok": True,
            "kind": "openai_compatible",
            "base_url": base,
            "model": pc.get("model"),
            "model_available": True,
            "note": f"models endpoint {exc.code}",
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "kind": "openai_compatible", "base_url": base, "error": str(exc)}


def probe_provider(name: str, pc: dict) -> dict:
    kind = pc.get("kind") or name
    if kind == "stub" or name == "stub":
        return {"ok": True, "kind": "stub", "name": name}
    if kind == "ollama":
        out = _probe_ollama(pc)
        out["name"] = name
        return out
    if kind in ("openai_compatible", "openai"):
        out = _probe_openai_compatible(name, pc)
        out["name"] = name
        return out
    return {"ok": False, "name": name, "kind": kind, "error": f"unknown kind {kind}"}


def probe_all(data_dir: str) -> dict:
    cfg = load_llm_config(data_dir)
    providers = cfg.get("providers") or {}
    order: List[str] = cfg.get("provider_priority") or []
    results = []
    active = None
    for name in order:
        if name not in providers:
            continue
        r = probe_provider(name, providers[name])
        results.append(r)
        if active is None and r.get("ok") and r.get("model_available", True):
            active = name
    rag = {}
    if (cfg.get("rag") or {}).get("enabled", True):
        from .rag.index import index_info

        rag = index_info(data_dir, cfg)
    return {
        "enabled": bool(cfg.get("enabled")),
        "active_provider": active,
        "provider_priority": order,
        "fallback_mode": "local_first" if order[:1] == ["local"] else "custom",
        "providers": results,
        "rag": rag,
        "ready": bool(cfg.get("enabled")) and active is not None,
    }
