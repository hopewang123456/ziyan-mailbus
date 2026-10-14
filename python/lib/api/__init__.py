"""
mailbus HTTP API 包

从 api_server.py 拆分而来，保持向后兼容。
"""

import os
import json
import sys
from http.server import HTTPServer
from socketserver import ThreadingMixIn

from lib import composition  # 跨层解耦：api→adapter 通过 composition 拿服务
from .base import MailbusAPIHandler


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器"""
    allow_reuse_address = True
    daemon_threads = True


def _connect_ok(family: int, addr: str, port: int) -> bool:
    """对 addr:port 做一次 TCP connect 探测，成功返回 True。"""
    import socket

    s = socket.socket(family, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect((addr, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _port_occupied(host: str, port: int) -> bool:
    """检测 host:port 是否已被监听（TCP connect 探测，跨平台）。

    用 connect 而非 bind 探测：Windows 下 SO_REUSEADDR 会让多个进程共享端口，
    而 TIME_WAIT 状态又会干扰 bind 探测；connect 只在真正有 LISTENING 时成功，
    可精确区分「已占用」与「仅 TIME_WAIT」，避免 watchdog 重启时误判。

    地址归一化：
      - localhost → 127.0.0.1（回环），与 127.0.0.1 等价；
      - 空 / 0.0.0.0 / * / :: → 通配，会绑定**所有**网卡，因此需探测
        回环 + 本机全部非回环 IP，任一被监听即视为冲突；
      - 具体 IP / 域名 → 仅探测该地址（0.0.0.0 通配已占用时，connect 具体
        地址同样会被接受，故一并覆盖）。

    保证 agent 既可接入本地（127.0.0.1 / 0.0.0.0 / localhost），也可接入
    外部 IP:port 时，不会因地址归一化不同而漏判重复。
    """
    import socket

    host = (host or "0.0.0.0").strip()
    if host.lower() == "localhost":
        host = "127.0.0.1"

    targets: list[tuple[int, str]] = []
    if host in ("0.0.0.0", "::", "*"):
        # 通配：覆盖回环 + 本机所有非回环 IPv4
        addrs: set[str] = {"127.0.0.1", "::1"}
        try:
            _name, _alias, resolved = socket.gethostbyname_ex(socket.gethostname())
        except OSError:
            resolved = []
        addrs.update(a for a in resolved if not a.startswith("127."))
        for addr in sorted(addrs):
            family = socket.AF_INET6 if ":" in addr else socket.AF_INET
            targets.append((family, addr))
    else:
        # 具体地址：getaddrinfo 解析域名 / IPv4 / IPv6
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError:
            return False
        for family, _st, _proto, _cn, sockaddr in infos:
            targets.append((family, sockaddr[0]))

    for family, addr in targets:
        if _connect_ok(family, addr, port):
            return True
    return False


def serve(data_dir: str, agents: dict, agent_types: dict = None,
          host: str = "127.0.0.1", port: int = None, token: str = "",
          config: dict = None):
    """启动 HTTP API 服务器（可选内置 scheduler）"""
    from lib.infra.constants import DEFAULT_API_PORT
    from lib.infra.utils import configure_stdio_utf8

    configure_stdio_utf8()
    if port is None:
        port = DEFAULT_API_PORT

    if _port_occupied(host, port):
        print(f"✗ {host}:{port} 已被占用（已有 mailbus serve 在运行）。", file=sys.stderr)
        print("  为避免多进程共享端口导致假死，请先停掉多余实例后再启动。", file=sys.stderr)
        raise SystemExit(1)

    try:
        # 跨层解耦：api→adapter 通过 composition 拿服务（2026-09 治理）
        from lib.composition import (
            bind_data_dir,
            ensure_framework_plugins_loaded,
            ensure_integration_plugins_loaded,
        )

        bind_data_dir(data_dir)
        ensure_framework_plugins_loaded(data_dir=data_dir, config=config)
        ensure_integration_plugins_loaded(data_dir=data_dir, config=config)
    except Exception:
        pass

    MailbusAPIHandler.data_dir = data_dir
    MailbusAPIHandler.agents = agents
    MailbusAPIHandler.agent_types = agent_types or {}
    # Prefer explicit token arg; else ensure/resolve from secrets / env / legacy
    try:
        from lib.application.mailbus_token import ensure_token, resolve_token

        resolved = (token or "").strip() or resolve_token(data_dir, config) or ensure_token(data_dir)
    except Exception:
        resolved = token or ""
    MailbusAPIHandler.auth_token = resolved
    MailbusAPIHandler.require_api_auth = bool((config or {}).get("require_api_auth", False))
    # 豁免 IP 白名单：config["auth"]["exempt_cidrs"] 或 config["exempt_cidrs"]
    _auth = (config or {}).get("auth") if isinstance((config or {}).get("auth"), dict) else {}
    _exempt = _auth.get("exempt_cidrs") or (config or {}).get("exempt_cidrs") or []
    if isinstance(_exempt, str):
        _exempt = [_exempt]
    MailbusAPIHandler.exempt_cidrs = [str(x).strip() for x in _exempt if str(x).strip()]

    # 公告板 + 权限文件路径
    paths = __import__("lib.infra.utils", fromlist=["resolve_paths"]).resolve_paths(data_dir)
    MailbusAPIHandler.bulletin_file = os.path.join(data_dir, "bulletin.json")
    MailbusAPIHandler.permission_file = os.path.join(data_dir, "permission.json")
    if not os.path.isfile(MailbusAPIHandler.permission_file):
        from lib.infra.utils import json_write, _now_iso
        from lib.infra.agent_demo import bulletin_default_list, bulletin_default_posters

        default_posters = bulletin_default_posters() or ["agent-a", "agent-m", "agent-g"]
        default_bulletin = bulletin_default_list() or ["agent-a", "agent-m"]
        default_perms = {
            name: {"browser": True, "desktop": True, "cli": True, "mailbox": True,
                   "bulletin": name in default_posters}
            for name in agents
        }
        json_write(MailbusAPIHandler.permission_file, {
            "permissions": default_perms,
            "bulletin": default_bulletin,
            "updated_at": _now_iso(),
        })

    hub = None
    if config:
        # 跨层解耦：api→adapter 通过 composition 拿服务
        SchedulerHub = composition.scheduler_hub_factory()
        hub = SchedulerHub(data_dir, config)
        hub.start()

    server = ThreadedHTTPServer((host, port), MailbusAPIHandler)
    print(f"🌐 API 服务已启动: http://{host}:{port}")
    print(f"   📋 API 端点: http://{host}:{port}/api/status")
    print(f"   📖 文档: http://{host}:{port}/")
    if token:
        print(f"   🔑 认证: Bearer token 已启用")

    # L0 faulthandler + L1 进程内看门狗（纯 Python，跨平台；均可用 env 关闭）
    try:
        from lib.application.ops.watchdog import enable_faulthandler, start_self_watchdog

        enable_faulthandler(data_dir)
        wt = start_self_watchdog(port, data_dir)
        if wt is not None:
            print("   🛡️ 自愈看门狗已启用（连续健康检查失败将 dump 现场并自尽，配合外部 watchdog 重启）")
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 API 服务已停止")
        if hub:
            hub.stop()
        server.server_close()

