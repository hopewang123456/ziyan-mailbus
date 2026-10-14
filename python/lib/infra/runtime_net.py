"""跨环境运行时网络原语 — windows / wsl / linux / docker 统一解析。

提供 5 个原语，供浏览器 URL 生成、探测 loopback 重写、白名单放行统一使用：

- ``runtime_env()``           → "windows" | "wsl" | "linux" | "docker"
- ``allowed_browser_hosts()`` → 白名单（IP/CIDR），来源 env > store/config.json
- ``browser_host()``          → 浏览器可达 host（白名单具体 IP > docker host.docker.internal > 127.0.0.1）
- ``browser_base_url()``      → 构造默认浏览器 URL
- ``rewrite_browser_host()``  → 重写 URL 里 loopback host（模板 URL 专用）
- ``resolve_loopback()``      → 探测前重写：docker 内 127.0.0.1 → host.docker.internal

本模块位于 infra 层，保持自包含，不 import 任何 adapters / application 模块。
"""

from __future__ import annotations

import ipaddress
import os
import sys
from urllib.parse import urlsplit, urlunsplit

from lib.infra.constants import MAILBUS_DATA_STR

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def _running_in_docker() -> bool:
    """mailbus 进程跑在 Docker 容器内。"""
    if os.path.isfile("/.dockerenv"):
        return True
    return os.path.isdir("/mailbus/store") and os.path.exists("/var/run/docker.sock")


def runtime_env() -> str:
    """运行时环境：windows | wsl | linux | docker。"""
    override = (os.environ.get("MAILBUS_RUNTIME") or "").strip().lower()
    if override in ("windows", "wsl", "linux", "docker"):
        return override
    if _running_in_docker():
        return "docker"
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "linux"  # 非 docker 主机，网络行为与 linux 一致
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as fh:
            if "microsoft" in fh.read().lower():
                return "wsl"
    except OSError:
        pass
    return "linux"


def _normalize_hosts(raw: object) -> list[str]:
    """把字符串/列表归一为去空的 host 列表（IP 或 CIDR）。"""
    if isinstance(raw, str):
        items = [p for p in raw.replace(";", ",").split(",")]
    elif isinstance(raw, (list, tuple, set)):
        items = [str(p) for p in raw]
    else:
        return []
    out: list[str] = []
    for item in items:
        host = item.strip()
        if not host:
            continue
        out.append(host)
    return out


def allowed_browser_hosts(data_dir: str | None = None) -> list[str]:
    """浏览器白名单：MAILBUS_BROWSER_HOSTS env > store/config.json browser_hosts > 空。

    元素为 IP 或 CIDR 网段（如 ``192.168.1.0/24``）。空 = 仅本机。
    """
    env_raw = (os.environ.get("MAILBUS_BROWSER_HOSTS") or "").strip()
    if env_raw:
        return _normalize_hosts(env_raw)
    cfg_hosts: list[str] = []
    try:
        from lib.infra.utils import json_read

        d = data_dir or os.environ.get("MAILBUS_DATA") or os.environ.get("MAILBUS_DATA_DIR") or MAILBUS_DATA_STR
        cfg = json_read(os.path.join(d, "config.json"), {})
        cfg_hosts = _normalize_hosts(cfg.get("browser_hosts") or [])
    except Exception:
        cfg_hosts = []
    return cfg_hosts


def _is_single_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _is_loopback(host: str) -> bool:
    if host in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _default_host() -> str:
    return "host.docker.internal" if runtime_env() == "docker" else "127.0.0.1"


def browser_host(*, authed: bool = False) -> str:
    """浏览器可达 host。

    - 白名单里有「具体 IP」（非 CIDR、非 loopback）且 authed=True → 用该 IP（局域网/广域网可达）
    - 否则（无白名单 / 全 CIDR / 未鉴权）→ docker 内 host.docker.internal，其余 127.0.0.1

    鉴权门槛：白名单非空（=非本机放行）但 ``authed`` 为 False 时退回本机 host，
    由调用方在 agent 已有浏览器凭据时传 ``authed=True``。
    """
    hosts = allowed_browser_hosts()
    if hosts:
        if authed:
            for h in hosts:
                if _is_single_ip(h) and not _is_loopback(h):
                    return h
        # 白名单仅含 CIDR 网段，或未鉴权 → 退回本机
        return _default_host()
    return _default_host()


def browser_base_url(port: int, *, path: str = "/", authed: bool = False) -> str:
    """构造默认浏览器 URL：http://<browser_host()>:<port><path>。"""
    if path and not path.startswith("/"):
        path = "/" + path
    return f"http://{browser_host(authed=authed)}:{port}{path}"


def _rewrite_target(authed: bool) -> str | None:
    """返回 loopback 模板 URL 的重写目标 host；None = 保持原样。"""
    hosts = allowed_browser_hosts()
    if hosts and authed:
        for h in hosts:
            if _is_single_ip(h) and not _is_loopback(h):
                return h
    if runtime_env() == "docker":
        return "host.docker.internal"
    return None


def rewrite_browser_host(url: str, *, authed: bool = False) -> str:
    """重写 URL 里的 loopback host（127.0.0.1/localhost），仅在需要跨环境时改动。

    用于 agent_types 里硬编码 ``http://127.0.0.1:{port}/``（或 localhost）的模板 URL：
    - 白名单命中具体 IP + authed → 白名单 IP（局域网/广域网放行）
    - docker 内 → host.docker.internal
    - 其余（非 docker、无白名单命中）→ 保持原样（localhost / 127.0.0.1 等价）
    非 loopback host（外部 URL）不改动。
    """
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    host = parts.hostname or ""
    if host not in ("127.0.0.1", "localhost", "::1"):
        return url
    target = _rewrite_target(authed=authed)
    if not target or target == host:
        return url
    netloc = parts.netloc.replace(host, target, 1)
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def resolve_loopback(url: str) -> str:
    """探测前重写：docker 容器内 127.0.0.1 指向容器自身，改写为 host.docker.internal。

    与 ``rewrite_browser_host`` 的区别：只处理 docker 场景，不引入白名单 host（探测从本进程发起）。
    """
    if not url or runtime_env() != "docker" or "127.0.0.1" not in url:
        return url
    return url.replace("127.0.0.1", "host.docker.internal")
