"""
ziyan-mailbus HTTP API — 基础请求处理器

包含: 认证、路由分发、静态文件服务、公共工具方法。
具体业务逻辑在 handlers_*.py 中。
"""

import os
import json
from http.server import BaseHTTPRequestHandler
from typing import Optional

# ── 处理器模块（延迟导入） ──
_handlers = None


def _get_handlers():
    global _handlers
    if _handlers is None:
        from . import handlers_inbox
        from . import handlers_system
        from . import handlers_tasks
        _handlers = {
            "inbox": handlers_inbox,
            "system": handlers_system,
            "tasks": handlers_tasks,
        }
    return _handlers



class MailbusAPIHandler(BaseHTTPRequestHandler):
    """HTTP API 请求处理器 — 路由分发中心"""

    data_dir = ""
    agents = {}
    agent_types = {}
    auth_token: Optional[str] = None
    bulletin_permit = []
    bulletin_authors = {}
    bulletin_file = ""
    permission_file = ""

    # ── 认证 ────────────────────────────────────────────────────────────

    def _check_auth(self) -> bool:
        if not self.auth_token:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:] == self.auth_token:
            return True
        if self.headers.get("X-API-Key") == self.auth_token:
            return True
        self._send_json({"error": "unauthorized"}, 401)
        return False



    # ── 公共工具 ────────────────────────────────────────────────────────

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _read_path(self):
        return self.path.split("?")[0].rstrip("/")

    def _read_post_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            body = self.rfile.read(content_length)
            try:
                return json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {}
        return {}

    def _serve_static(self, path: str) -> bool:
        if ".." in path or "~" in path:
            return False
        docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "docs")
        filename = "index.html" if path in ("", "/") else path.lstrip("/")
        abs_path = os.path.normpath(os.path.join(docs_dir, filename))
        if not abs_path.startswith(os.path.normpath(docs_dir)):
            return False
        try:
            with open(abs_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", self._guess_mime(filename))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            if filename == "index.html":
                import time
                buster = str(int(time.time()))
                content = content.replace(b'loadAll();', b'// cb=' + buster.encode() + b'\nloadAll();')
            self.end_headers()
            self.wfile.write(content)
            return True
        except (OSError, IOError):
            return False

    @staticmethod
    def _guess_mime(filename: str) -> str:
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        return {
            "html": "text/html; charset=utf-8",
            "js": "application/javascript; charset=utf-8",
            "css": "text/css; charset=utf-8",
            "json": "application/json; charset=utf-8",
            "png": "image/png",
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "svg": "image/svg+xml",
            "ico": "image/x-icon", "md": "text/markdown; charset=utf-8",
        }.get(ext, "application/octet-stream")

    # ── HTTP GET 路由 ──────────────────────────────────────────────────

    def do_GET(self):
        if not self._check_auth():
            return
        path = self._read_path()
        h = _get_handlers()

        routes = {
            "/api/status": lambda: h["system"].handle_status(self),
            "/api/agents": lambda: h["system"].handle_agents(self),
            "/api/tasks": lambda: h["tasks"].handle_tasks(self),
            "/api/heartbeat": lambda: h["system"].handle_heartbeat(self),
            "/api/alerts": lambda: h["system"].handle_alerts(self),
            "/api/config": lambda: h["system"].handle_config(self),
            "/api/launch": lambda: h["system"].handle_list_launchable(self),
            "/api/bulletin": lambda: h["tasks"].handle_bulletin(self),
            "/api/bulletin/permit": lambda: self._send_json({"permit": self.bulletin_permit}),
            "/api/permission": lambda: h["tasks"].handle_permission(self),
            "/api/reports": lambda: h["system"].handle_reports(self),
            "/api/replies": lambda: h["inbox"].handle_replies(self),
            "/api/skill-usage": lambda: h["tasks"].handle_skill_usage(self),
            "/api/skill-use": lambda: h["tasks"].handle_skill_use(self),
            "/api/templates": lambda: h["system"].handle_templates(self),
            "/api/send-msg": lambda: h["inbox"].handle_send_msg(self),
        }

        if path in routes:
            routes[path]()
        elif path.startswith("/api/inbox/"):
            h["inbox"].handle_inbox(self, path[len("/api/inbox/"):])
        elif path.startswith("/api/agent-profile/"):
            h["system"].handle_agent_profile(self, path[len("/api/agent-profile/"):])
        elif path.startswith("/api/ping/"):
            h["system"].handle_ping(self, path[len("/api/ping/"):])
        elif path.startswith("/api/search"):
            h["system"].handle_search(self)
        elif path in ("", "/"):
            self._serve_static("/")
        elif path == "/index.html":
            self._serve_static("/")
        elif path == "/ping-test":
            self._send_json({
                "version": "v2.0.0",
                "agents": len(self.agents),
            })
        elif not self._serve_static(path):
            self._send_json({"error": "not_found", "path": path}, 404)

    # ── HTTP POST 路由 ─────────────────────────────────────────────────

    def do_POST(self):
        if not self._check_auth():
            return
        path = self._read_path()
        h = _get_handlers()

        if path == "/api/launch":
            h["system"].handle_launch(self)
        elif path == "/api/bulletin/post":
            h["tasks"].handle_bulletin_post(self)
        elif path == "/api/bulletin/permit":
            h["tasks"].handle_bulletin_permit(self)
        elif path == "/api/permission":
            h["tasks"].handle_permission(self)
        elif path == "/api/skill-use":
            h["tasks"].handle_skill_use(self)
        elif path == "/api/send-msg":
            h["inbox"].handle_send_msg(self)
        elif path.startswith("/api/actions/update/"):
            parts = path.split("/")
            if len(parts) >= 5:
                h["inbox"].handle_actions_update(self, parts[3], parts[4])
            else:
                self._send_json({"error": "bad_path"}, 400)
        elif path.startswith("/api/mark-read/"):
            h["inbox"].handle_mark_read(self, path[len("/api/mark-read/"):])
        else:
            self._send_json({"error": "not_found"}, 404)

    # ── CORS ───────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.end_headers()

