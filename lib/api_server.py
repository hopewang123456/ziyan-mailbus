"""ziyan-mailbus HTTP API (deprecated — 已迁移至 lib.api)"""
import warnings
from http.server import HTTPServer
from socketserver import ThreadingMixIn


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器"""
    allow_reuse_address = True
    daemon_threads = True


def serve(data_dir, agents, agent_types,
          host="127.0.0.1", port=9812, token=""):
    """启动 HTTP API 服务（已迁移至 lib.api 包）"""
    warnings.warn("api_server.serve 已迁移至 lib.api.serve，请更新导入", DeprecationWarning, stacklevel=2)
    from lib.api import serve as new_serve
    new_serve(data_dir, agents, agent_types or {}, host=host, port=port, token=token)
