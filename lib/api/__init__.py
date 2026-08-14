"""
mailbus HTTP API 包

从 api_server.py 拆分而来，保持向后兼容。
"""

import os
import json
from http.server import HTTPServer
from socketserver import ThreadingMixIn

from .base import MailbusAPIHandler


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器"""
    allow_reuse_address = True
    daemon_threads = True


def serve(data_dir: str, agents: dict, agent_types: dict = None,
          host: str = "127.0.0.1", port: int = None, token: str = "",
          config: dict = None):
    """启动 HTTP API 服务器（可选内置 scheduler）"""
    from lib.infra.constants import DEFAULT_API_PORT
    from lib.infra.utils import configure_stdio_utf8

    configure_stdio_utf8()
    if port is None:
        port = DEFAULT_API_PORT

    try:
        from lib.adapters.frameworks.entry_point_discovery import ensure_framework_plugins_loaded
        from lib.adapters.integrations.entry_point_discovery import ensure_integration_plugins_loaded
        from lib.composition import bind_data_dir

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
        from lib.adapters.ops.scheduler import SchedulerHub
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

