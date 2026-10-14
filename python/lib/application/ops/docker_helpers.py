"""Cross-platform docker helpers — replace docker-agents/*.ps1 business glue."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from lib.infra.env_bootstrap import mailbus_paths
from lib.infra import mbus_log


def _compose_dir() -> Path:
    return Path(mailbus_paths()["compose_dir"])


def _docker_argv(*args: str) -> list[str]:
    """Local docker, or Windows → wsl -e docker (no adapters import)."""
    if shutil.which("docker"):
        return ["docker", *args]
    if os.name == "nt":
        wsl = shutil.which("wsl") or shutil.which("wsl.exe")
        if wsl:
            return [wsl, "-e", "docker", *args]
    return ["docker", *args]


def _run(cmd: list[str], *, cwd: Path | None = None) -> int:
    mbus_log.info("+ %s", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None).returncode


def restart_mailbus_container() -> int:
    """Restart mailbus service in docker-agents compose project."""
    d = _compose_dir()
    rc = _run(_docker_argv("compose", "restart", "mailbus"), cwd=d)
    if rc != 0:
        return rc
    port = os.environ.get("MAILBUS_API_PORT") or mailbus_paths().get("api_port") or "9814"
    mbus_log.info("mailbus restarted — API: http://127.0.0.1:%s/", port)
    return 0


def start_n8n() -> int:
    """docker compose -f docker-compose.n8n.yml up -d"""
    d = _compose_dir()
    compose = d / "docker-compose.n8n.yml"
    if not compose.is_file():
        mbus_log.error("missing %s", compose)
        return 1
    rc = _run(_docker_argv("compose", "-f", str(compose), "up", "-d"), cwd=d)
    if rc == 0:
        mbus_log.info("n8n UI: http://127.0.0.1:5678")
    return rc


def up_comfyui_gpu() -> int:
    """Bring up ComfyUI GPU compose (Linux/WSL-friendly)."""
    d = _compose_dir()
    compose = d / "docker-compose.comfyui-gpu.yml"
    if not compose.is_file():
        mbus_log.error("missing %s", compose)
        return 1
    rc = _run(_docker_argv("compose", "-f", str(compose), "up", "-d"), cwd=d)
    if rc == 0:
        mbus_log.info("ComfyUI: http://127.0.0.1:8188")
    return rc


def ensure_ollama_cli(*, data_dir: str = "", no_pull: bool = True, wait_seconds: int = 90) -> int:
    """Delegate to tools/ensure-ollama.py (cross-platform)."""
    root = Path(mailbus_paths()["root"])
    script = root / "tools" / "ensure-ollama.py"
    if not script.is_file():
        mbus_log.error("missing %s", script)
        return 2
    data = data_dir or mailbus_paths()["data_dir"]
    cmd = [sys.executable, str(script), "--data-dir", data, "--wait-seconds", str(wait_seconds)]
    if no_pull:
        cmd.append("--no-pull")
    return _run(cmd, cwd=root)
