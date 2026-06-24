"""Ensure stock Ollama is reachable — mailbus adapter only.

Does NOT patch, fork, or vendor Ollama. Only:
- probe official HTTP API (/api/tags)
- optionally invoke host ``ollama serve`` / ``ollama pull`` binaries
- read model/base_url from mailbus config
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from typing import List, Optional, Tuple


def find_ollama_bin() -> Optional[str]:
    env = os.environ.get("OLLAMA_BIN")
    if env and os.path.isfile(env):
        return env
    if platform.system() == "Windows":
        for p in (
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe"),
        ):
            if p and os.path.isfile(p):
                return p
    return shutil.which("ollama")


def probe_tags(base_url: str, timeout: float = 5) -> Tuple[bool, List[str]]:
    try:
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        models = [m.get("name") for m in (data.get("models") or []) if m.get("name")]
        return True, models
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
        return False, []


def model_present(models: List[str], model: str) -> bool:
    if not model:
        return True
    return any(model in m or m.startswith(model + ":") for m in models)


def start_daemon(ollama_bin: str) -> None:
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if platform.system() == "Windows":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    subprocess.Popen([ollama_bin, "serve"], **kwargs)


def wait_for_api(base_url: str, max_wait: float = 60, interval: float = 2) -> bool:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        ok, _ = probe_tags(base_url, timeout=3)
        if ok:
            return True
        time.sleep(interval)
    return False


def pull_model(ollama_bin: str, model: str, timeout: float = 900) -> bool:
    try:
        subprocess.run([ollama_bin, "pull", model], check=True, timeout=timeout)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def ensure_ollama(
    base_url: str = "http://127.0.0.1:11434",
    model: str = "",
    *,
    start: bool = True,
    pull: bool = True,
    wait_seconds: float = 60,
) -> dict:
    ollama_bin = find_ollama_bin()
    result: dict = {"ok": False, "base_url": base_url, "model": model, "ollama_bin": ollama_bin}

    ok, models = probe_tags(base_url)
    if not ok and start:
        if not ollama_bin:
            result["error"] = "ollama binary not found"
            return result
        start_daemon(ollama_bin)
        ok = wait_for_api(base_url, max_wait=wait_seconds)
        models = probe_tags(base_url)[1] if ok else []

    if not ok:
        result["error"] = "ollama API unreachable"
        return result

    result["models_count"] = len(models)
    if model and not model_present(models, model):
        if pull:
            if not ollama_bin:
                result["error"] = "ollama binary not found for pull"
                result["model_available"] = False
                return result
            if not pull_model(ollama_bin, model):
                result["error"] = f"failed to pull model {model}"
                result["model_available"] = False
                return result
            models = probe_tags(base_url)[1]
        if not model_present(models, model):
            result["error"] = f"model {model} not available"
            result["model_available"] = False
            return result

    result["ok"] = True
    result["model_available"] = model_present(models, model) if model else True
    return result


def ensure_from_config(data_dir: str, **kwargs) -> dict:
    from .planner_llm import load_llm_config

    cfg = load_llm_config(data_dir)
    if not cfg.get("enabled"):
        return {"ok": True, "skipped": True, "reason": "internal_llm disabled"}
    local = (cfg.get("providers") or {}).get("local") or {}
    if local.get("kind") != "ollama":
        return {"ok": True, "skipped": True, "reason": "local provider is not ollama"}
    return ensure_ollama(
        base_url=local.get("base_url") or "http://127.0.0.1:11434",
        model=local.get("model") or "",
        **kwargs,
    )
