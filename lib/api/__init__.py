"""
ziyan-mailbus HTTP API 包

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
    from lib.constants import DEFAULT_API_PORT
    from lib.utils import configure_stdio_utf8

    configure_stdio_utf8()
    if port is None:
        port = DEFAULT_API_PORT
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

    # 公告板 + 权限文件路径
    paths = __import__("lib.utils", fromlist=["resolve_paths"]).resolve_paths(data_dir)
    MailbusAPIHandler.bulletin_file = os.path.join(data_dir, "bulletin.json")
    MailbusAPIHandler.permission_file = os.path.join(data_dir, "permission.json")
    if not os.path.isfile(MailbusAPIHandler.permission_file):
        from lib.utils import json_write, _now_iso
        default_perms = {
            name: {"browser": True, "desktop": True, "cli": True, "mailbox": True,
                   "bulletin": name in ("lingzhao", "xiaoqi", "lingxiao")}
            for name in agents
        }
        json_write(MailbusAPIHandler.permission_file, {
            "permissions": default_perms,
            "bulletin": ["lingzhao", "xiaoqi"],
            "updated_at": _now_iso(),
        })

    hub = None
    if config:
        from lib.scheduler import SchedulerHub
        hub = SchedulerHub(data_dir, config)
        hub.start()

    server = ThreadedHTTPServer((host, port), MailbusAPIHandler)
    print(f"🌐 API 服务已启动: http://{host}:{port}")
    print(f"   📋 API 端点: http://{host}:{port}/api/status")
    print(f"   📖 文档: http://{host}:{port}/")
    if token:
        print(f"   🔑 认证: Bearer token 已启用")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 API 服务已停止")
        if hub:
            hub.stop()
        server.server_close()

