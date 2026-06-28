"""Docker 容器探测 — Windows 宿主经 WSL 回退。"""

from __future__ import annotations

import shutil
import subprocess


def docker_exec_ps(container: str, *, timeout: int = 8) -> str:
    """在容器内执行 ps aux；失败返回空串。"""
    if not container:
        return ""
    attempts = []
    docker = shutil.which("docker")
    if docker:
        attempts.append([docker, "exec", container, "ps", "aux"])
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if wsl:
        attempts.append([wsl, "-e", "docker", "exec", container, "ps", "aux"])
    for argv in attempts:
        try:
            r = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except Exception:
            continue
    return ""
