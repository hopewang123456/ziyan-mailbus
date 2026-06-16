"""宿主机权限辅助 — Docker mailbus 优先，其次 WSL sudo（密码来自 .env.secrets）。"""
from __future__ import annotations

import os
import subprocess
from typing import Optional


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _secrets_path() -> str:
    return os.environ.get(
        "MAILBUS_SECRETS",
        os.path.join(_repo_root(), "docker-agents", ".env.secrets"),
    )


def load_sudo_password() -> Optional[str]:
    if os.environ.get("SUDO_PASSWORD"):
        return os.environ["SUDO_PASSWORD"]
    path = _secrets_path()
    if not os.path.isfile(path):
        return None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("SUDO_PASSWORD="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def docker_mailbus_exec(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "exec", "docker-agents-mailbus-1", *args],
        capture_output=True, text=True, timeout=timeout,
    )


def write_via_mailbus_container(host_path: str, content: str) -> bool:
    """容器内 root 写挂载卷（避免 WSL 上 root 属主文件无法写）。"""
    if not host_path.startswith("/mnt/e/ai_tools/mail/"):
        return False
    container_path = host_path.replace("/mnt/e/ai_tools/mail", "/mailbus", 1)
    try:
        r = docker_mailbus_exec(
            ["python3", "-c", f"open({container_path!r},'w',encoding='utf-8').write({content!r})"],
        )
        return r.returncode == 0
    except Exception:
        return False


def chown_store_path(host_path: str, user: str = "hopewang123456") -> bool:
    wsl_sudo = os.path.join(_repo_root(), "docker-agents", "wsl-sudo.sh")
    if not os.path.isfile(wsl_sudo):
        return False
    pw = load_sudo_password()
    if not pw:
        return False
    env = os.environ.copy()
    env["SUDO_PASSWORD"] = pw
    try:
        r = subprocess.run(
            ["bash", wsl_sudo, "chown", f"{user}:{user}", host_path],
            env=env, capture_output=True, text=True, timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return False
