"""Host plane — argv start/stop on host or via WSL (no shell=True)."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Any

from lib.adapters.frameworks.support import assert_spawn_argv_allowed
from lib.domain.types import PlaneActionResult, ProbeResult
from lib.infra.utils import json_read


def _normalize_cmd(cmd: Any) -> list[str] | None:
    if not cmd:
        return None
    if isinstance(cmd, list):
        return [str(x) for x in cmd if str(x)]
    if isinstance(cmd, str) and cmd.strip():
        # refuse shell strings — must be list from API/config
        return None
    return None


def _run_argv(argv: list[str], *, cwd: str | None = None, timeout: int = 120) -> tuple[int, str]:
    try:
        r = subprocess.run(
            argv,
            cwd=cwd or None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
        detail = ((r.stderr or "") + "\n" + (r.stdout or "")).strip()
        return r.returncode, detail[:500]
    except Exception as exc:
        return 1, str(exc)


class HostPlane:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def _entry(self, framework: str) -> dict[str, Any]:
        cfg = json_read(os.path.join(self.data_dir, "config.json"), {})
        return dict((cfg.get("frameworks") or {}).get(framework) or {})

    def _cfg(self) -> dict:
        return json_read(os.path.join(self.data_dir, "config.json"), {})

    def start_framework(self, framework: str) -> PlaneActionResult:
        entry = self._entry(framework)
        argv = _normalize_cmd(entry.get("start_cmd") or entry.get("host_start_cmd"))
        if not argv:
            # optional WSL helper script
            script = str(entry.get("wsl_start_script") or "").strip()
            if script:
                wsl = shutil.which("wsl.exe") or shutil.which("wsl")
                if not wsl:
                    return PlaneActionResult(ok=False, framework=framework, detail="wsl_missing")
                argv = [wsl, "-e", "bash", script]
            else:
                return PlaneActionResult(ok=True, framework=framework, detail="no_host_start_cmd")
        try:
            assert_spawn_argv_allowed(argv, self._cfg())
        except Exception as exc:
            return PlaneActionResult(ok=False, framework=framework, detail=str(exc))
        cwd = str(entry.get("root_path") or entry.get("cwd") or "") or None
        last = ""
        for attempt in range(1, 4):
            code, detail = _run_argv(argv, cwd=cwd, timeout=120)
            last = detail or f"exit={code}"
            if code == 0:
                probe = self.probe_framework(framework)
                if probe.ok or not entry.get("health_url"):
                    return PlaneActionResult(ok=True, framework=framework, detail=f"started:{attempt}")
            time.sleep(2)
        return PlaneActionResult(ok=False, framework=framework, detail=last)

    def stop_framework(self, framework: str) -> PlaneActionResult:
        entry = self._entry(framework)
        argv = _normalize_cmd(entry.get("stop_cmd") or entry.get("host_stop_cmd"))
        if not argv:
            script = str(entry.get("wsl_stop_script") or "").strip()
            if script:
                wsl = shutil.which("wsl.exe") or shutil.which("wsl")
                if not wsl:
                    return PlaneActionResult(ok=False, framework=framework, detail="wsl_missing")
                argv = [wsl, "-e", "bash", script]
            else:
                return PlaneActionResult(ok=True, framework=framework, detail="no_host_stop_cmd")
        try:
            assert_spawn_argv_allowed(argv, self._cfg())
        except Exception as exc:
            return PlaneActionResult(ok=False, framework=framework, detail=str(exc))
        cwd = str(entry.get("root_path") or entry.get("cwd") or "") or None
        code, detail = _run_argv(argv, cwd=cwd, timeout=120)
        return PlaneActionResult(ok=code == 0, framework=framework, detail=detail or f"exit={code}")

    def probe_framework(self, framework: str) -> ProbeResult:
        entry = self._entry(framework)
        health_url = str(entry.get("health_url") or "").strip()
        if health_url:
            from lib.adapters.plane.probe import probe_http

            ok = probe_http(health_url)
            return ProbeResult(ok=ok, agent_id=framework, detail=health_url if ok else "health_fail")
        # no health → assume ok after start (host processes vary)
        return ProbeResult(ok=True, agent_id=framework, detail="no_health_url")
