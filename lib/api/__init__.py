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
          host: str = "127.0.0.1", port: int = 9812, token: str = "",
          config: dict = None):
    """启动 HTTP API 服务器（可选内置 scheduler）"""
    MailbusAPIHandler.data_dir = data_dir
    MailbusAPIHandler.agents = agents
    MailbusAPIHandler.agent_types = agent_types or {}
    MailbusAPIHandler.auth_token = token

    # 公告板 + 权限文件路径
    paths = __import__("lib.utils", fromlist=["resolve_paths"]).resolve_paths(data_dir)
    MailbusAPIHandler.bulletin_file = os.path.join(data_dir, "bulletin.json")
    MailbusAPIHandler.permission_file = os.path.join(data_dir, "permission.json")

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

