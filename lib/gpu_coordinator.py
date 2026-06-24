"""8GB GPU 分时协调 — ComfyUI 与 Ollama 互斥占用显存。

mailbus 不 patch ComfyUI/Ollama；仅通过官方 HTTP API 释放 VRAM。
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

_lock = threading.Lock()
_owner: Optional[str] = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _resolve_env(key: str, default: str = "") -> str:
    if not key:
        return default
    return (os.environ.get(key) or default).strip()


def _load_store_config(data_dir: str) -> dict:
    path = os.path.join(data_dir, "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def load_gpu_sharing_config(cfg: Optional[dict] = None) -> dict:
    """合并 env + config.json 的 gpu_sharing / mailbus_internal_llm.gpu_sharing。"""
    block: dict = {}
    if cfg:
        block = dict(cfg.get("gpu_sharing") or {})
        inner = cfg.get("mailbus_internal_llm") or {}
        if isinstance(inner, dict) and inner.get("gpu_sharing"):
            for k, v in (inner.get("gpu_sharing") or {}).items():
                block.setdefault(k, v)

    enabled = block.get("enabled")
    if enabled is None:
        enabled = _env_bool("MAILBUS_GPU_SHARING", True)
    else:
        enabled = bool(enabled)

    return {
        "enabled": enabled,
        "mode": block.get("mode") or os.environ.get("MAILBUS_GPU_SHARING_MODE") or "time_share",
        "settle_seconds": float(
            block.get("settle_seconds")
            or os.environ.get("MAILBUS_GPU_SETTLE_SECONDS")
            or 2
        ),
        "comfyui_base_url": _resolve_env(
            block.get("comfyui_base_url_env") or "COMFYUI_BASE_URL",
            block.get("comfyui_base_url") or "http://127.0.0.1:8188",
        ),
        "ollama_base_url": _resolve_env(
            block.get("ollama_base_url_env") or "MAILBUS_OLLAMA_BASE_URL",
            block.get("ollama_base_url") or "http://127.0.0.1:11434",
        ),
        "release_ollama_before_image": block.get("release_ollama_before_image", True),
        "release_comfyui_before_llm": block.get("release_comfyui_before_llm", True),
        "release_comfyui_after_image": block.get("release_comfyui_after_image", True),
        "release_ollama_after_llm": block.get("release_ollama_after_llm", False),
    }


def _http_json(
    url: str,
    payload: Optional[dict] = None,
    *,
    method: str = "GET",
    timeout: float = 10,
) -> tuple[bool, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return True, json.loads(body) if body else {}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return False, None


def list_ollama_loaded_models(base_url: str) -> List[str]:
    ok, body = _http_json(f"{base_url.rstrip('/')}/api/ps")
    if not ok or not isinstance(body, dict):
        return []
    out: List[str] = []
    for row in body.get("models") or []:
        name = row.get("name") or row.get("model")
        if name:
            out.append(str(name))
    return out


def release_ollama_vram(base_url: str, models: Optional[List[str]] = None) -> dict:
    """卸载 Ollama 已加载模型（keep_alive=0）。"""
    base = base_url.rstrip("/")
    targets = models if models is not None else list_ollama_loaded_models(base)
    released: List[str] = []
    errors: List[str] = []
    for model in targets:
        ok, _ = _http_json(
            f"{base}/api/generate",
            {"model": model, "prompt": "", "keep_alive": 0},
            method="POST",
            timeout=15,
        )
        if ok:
            released.append(model)
        else:
            errors.append(model)
    return {"ok": not errors or bool(released), "released": released, "errors": errors}


def release_comfyui_vram(base_url: str) -> dict:
    """ComfyUI POST /free — 卸载 checkpoint / 释放显存。"""
    ok, body = _http_json(
        f"{base_url.rstrip('/')}/free",
        {"unload_models": True, "free_memory": True},
        method="POST",
        timeout=15,
    )
    return {"ok": ok, "body": body}


def _settle(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def acquire_gpu(owner: str, cfg: Optional[dict] = None) -> dict:
    """owner: ``comfyui`` | ``ollama``"""
    gs = load_gpu_sharing_config(cfg)
    if not gs["enabled"] or gs["mode"] != "time_share":
        return {"ok": True, "skipped": True, "reason": "gpu_sharing_disabled"}

    global _owner
    with _lock:
        if _owner and _owner != owner:
            return {
                "ok": False,
                "error": "gpu_busy",
                "message": f"GPU 正被 {_owner} 占用，请稍后重试",
                "owner": _owner,
            }
        _owner = owner

    actions: dict = {"owner": owner, "steps": []}
    try:
        if owner == "comfyui" and gs["release_ollama_before_image"]:
            step = release_ollama_vram(gs["ollama_base_url"])
            actions["steps"].append({"release_ollama": step})
        elif owner == "ollama" and gs["release_comfyui_before_llm"]:
            step = release_comfyui_vram(gs["comfyui_base_url"])
            actions["steps"].append({"release_comfyui": step})
        _settle(gs["settle_seconds"])
        actions["ok"] = True
        return actions
    except Exception as exc:
        with _lock:
            if _owner == owner:
                _owner = None
        return {"ok": False, "error": "acquire_failed", "message": str(exc)}


def release_gpu(owner: str, cfg: Optional[dict] = None) -> dict:
    gs = load_gpu_sharing_config(cfg)
    global _owner
    actions: dict = {"owner": owner, "steps": []}

    with _lock:
        if _owner != owner:
            return {"ok": True, "skipped": True, "reason": "not_owner", "owner": _owner}
        _owner = None

    if not gs["enabled"] or gs["mode"] != "time_share":
        return {"ok": True, "skipped": True}

    try:
        if owner == "comfyui" and gs["release_comfyui_after_image"]:
            step = release_comfyui_vram(gs["comfyui_base_url"])
            actions["steps"].append({"release_comfyui": step})
        elif owner == "ollama" and gs["release_ollama_after_llm"]:
            step = release_ollama_vram(gs["ollama_base_url"])
            actions["steps"].append({"release_ollama": step})
        actions["ok"] = True
        return actions
    except Exception as exc:
        return {"ok": False, "error": "release_failed", "message": str(exc)}


@contextmanager
def gpu_lease(owner: str, cfg: Optional[dict] = None) -> Iterator[dict]:
    meta = acquire_gpu(owner, cfg)
    if not meta.get("ok") and not meta.get("skipped"):
        raise RuntimeError(meta.get("message") or meta.get("error") or "gpu_acquire_failed")
    try:
        yield meta
    finally:
        release_gpu(owner, cfg)


def reset_gpu_lock_for_tests() -> None:
    global _owner
    with _lock:
        _owner = None
