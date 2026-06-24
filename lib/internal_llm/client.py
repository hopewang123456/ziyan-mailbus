"""Internal LLM provider 链 — local · remote · stub。"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


class LLMError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise LLMError("llm_empty_response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        raise LLMError("llm_invalid_json", text[:200])


def _stub_complete(messages: List[dict], provider_cfg: dict) -> str:
    """CI / 无网络时的确定性 Planner 输出。"""
    user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user = m.get("content") or ""
            break
    intent = user.lower()
    if any(k in intent for k in ("redis", "缓存", "cache", "架构", "调研", "评估")):
        chain = [3, 1, 8, 5, 12]
        guess = "custom"
    elif any(k in intent for k in ("安全", "security", "漏洞")):
        chain = [2, 5, 9]
        guess = "security_review"
    else:
        chain = [3, 1, 9]
        guess = "spike"
    reasons = {
        3: "technical research for unknown/custom intent",
        1: "solution design after research",
        8: "implementation",
        5: "code review",
        12: "acceptance",
        2: "security audit",
        9: "ops handoff",
    }
    out = {
        "planned_chain": [
            {"role_type": rt, "reason": reasons.get(rt, f"role_type {rt}")}
            for rt in chain
        ],
        "plan_meta": {
            "method": "internal_llm",
            "task_type_guess": guess,
            "confidence": 0.72,
            "provider_used": "local",
            "model": "stub",
        },
    }
    return json.dumps(out, ensure_ascii=False)


def _ollama_complete(messages: List[dict], provider_cfg: dict) -> str:
    """Stock Ollama /api/chat adapter — no Ollama-side patches."""
    base = (provider_cfg.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
    model = provider_cfg.get("model") or "qwen2.5:3b-instruct-q4_K_M"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": float(provider_cfg.get("temperature") or 0.1),
            "num_predict": int(provider_cfg.get("max_tokens") or 1024),
        },
    }
    req = urllib.request.Request(
        f"{base}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = int(provider_cfg.get("timeout_seconds") or 60)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    msg = (data.get("message") or {}).get("content") or ""
    return msg


def _openai_compatible_complete(messages: List[dict], provider_cfg: dict) -> str:
    base = (provider_cfg.get("base_url") or "").rstrip("/")
    if not base:
        raise LLMError("llm_config", "missing base_url")
    env_key = provider_cfg.get("api_key_env") or "MAILBUS_INTERNAL_LLM_API_KEY"
    api_key = os.environ.get(env_key) or provider_cfg.get("api_key") or ""
    if not api_key:
        raise LLMError("llm_no_api_key", env_key)
    model = provider_cfg.get("model") or "deepseek-chat"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(provider_cfg.get("temperature") or 0.1),
        "max_tokens": int(provider_cfg.get("max_tokens") or 2048),
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    timeout = int(provider_cfg.get("timeout_seconds") or 90)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    choices = data.get("choices") or []
    if not choices:
        raise LLMError("llm_empty_response")
    return (choices[0].get("message") or {}).get("content") or ""


def complete(
    messages: List[dict],
    cfg: dict,
    *,
    prefer: Optional[str] = None,
) -> Tuple[dict, str]:
    """调用 provider 链，返回 (parsed_json, provider_used)。"""
    providers = cfg.get("providers") or {}
    order = cfg.get("provider_priority") or ["local", "remote"]
    if prefer:
        order = [prefer] + [p for p in order if p != prefer]

    guard = cfg.get("guardrails") or {}
    per_provider_retries = max(1, int(guard.get("max_retries") or 1) + 1)
    errors = []
    for name in order:
        pc = providers.get(name) or {}
        kind = pc.get("kind") or name
        for attempt in range(1, per_provider_retries + 1):
            try:
                if kind == "stub" or name == "stub":
                    raw = _stub_complete(messages, pc)
                    used = "local"
                elif kind == "ollama":
                    from ..gpu_coordinator import acquire_gpu, release_gpu

                    acq = acquire_gpu("ollama", cfg)
                    if not acq.get("ok") and not acq.get("skipped"):
                        raise LLMError("gpu_busy", acq.get("message") or "GPU 被占用")
                    try:
                        raw = _ollama_complete(messages, pc)
                    finally:
                        release_gpu("ollama", cfg)
                    used = "local"
                elif kind in ("openai_compatible", "openai"):
                    raw = _openai_compatible_complete(messages, pc)
                    used = "remote"
                else:
                    errors.append(f"{name}: unknown kind {kind}")
                    break
                return _extract_json(raw), used
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, LLMError) as exc:
                tag = f"{name}#{attempt}" if per_provider_retries > 1 else name
                errors.append(f"{tag}: {exc}")
                if attempt < per_provider_retries:
                    continue
                break
            except json.JSONDecodeError as exc:
                tag = f"{name}#{attempt}" if per_provider_retries > 1 else name
                errors.append(f"{tag}: json {exc}")
                if attempt < per_provider_retries:
                    continue
                break

    raise LLMError("llm_unavailable", "; ".join(errors[-3:]))
