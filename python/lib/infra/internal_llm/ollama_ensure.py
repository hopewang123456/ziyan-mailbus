"""Ensure Ollama daemon + model from mailbus_internal_llm config."""

from __future__ import annotations

from lib.infra.clock import now_dt, now_ts, now_utc_dt
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

from lib.adapters.internal_llm.probe import load_llm_config, probe_provider


def _ollama_provider(cfg: dict) -> dict | None:
    providers = cfg.get("providers") or {}
    for name in cfg.get("provider_priority") or ["local"]:
        pc = providers.get(name) or {}
        if (pc.get("kind") or name) == "ollama":
            return pc
    for name, pc in providers.items():
        if isinstance(pc, dict) and (pc.get("kind") or name) == "ollama":
            return pc
    return None


def ensure_from_config(
    data_dir: str,
    *,
    start: bool = True,
    pull: bool = True,
    wait_seconds: float = 60,
) -> dict:
    cfg = load_llm_config(data_dir)
    if not cfg.get("enabled"):
        return {"skipped": True, "reason": "mailbus_internal_llm disabled"}

    pc = _ollama_provider(cfg)
    if not pc:
        return {"skipped": True, "reason": "no ollama provider in config"}

    base = (pc.get("base_url") or os.environ.get("MAILBUS_OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    model = (pc.get("model") or os.environ.get("MAILBUS_OLLAMA_MODEL") or "").strip()
    probe = probe_provider("local", {**pc, "kind": "ollama", "base_url": base, "model": model})

    if probe.get("ok") and probe.get("model_available", True):
        return {"ok": True, "base_url": base, "model": model or probe.get("model")}

    if not start:
        return {"ok": False, "base_url": base, "model": model, "error": probe.get("error", "ollama not ready")}

    ollama_exe = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
    if os.path.isfile(ollama_exe):
        try:
            subprocess.Popen(
                [ollama_exe, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            return {"ok": False, "error": f"start failed: {exc}"}

    deadline = now_ts() + max(5.0, float(wait_seconds))
    while now_ts() < deadline:
        probe = probe_provider("local", {**pc, "kind": "ollama", "base_url": base, "model": model})
        if probe.get("ok"):
            break
        time.sleep(2.0)
    else:
        return {"ok": False, "base_url": base, "error": "ollama api timeout"}

    if model and pull and not probe.get("model_available", True):
        try:
            subprocess.run(
                [ollama_exe, "pull", model] if os.path.isfile(ollama_exe) else ["ollama", "pull", model],
                capture_output=True,
                timeout=max(120, int(wait_seconds)),
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass
        probe = probe_provider("local", {**pc, "kind": "ollama", "base_url": base, "model": model})

    if probe.get("ok"):
        return {"ok": True, "base_url": base, "model": model or probe.get("model")}
    return {"ok": False, "base_url": base, "model": model, "error": probe.get("error", "model unavailable")}
