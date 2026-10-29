"""
mailbus HTTP API — 基础请求处理器

包含: 认证、路由分发、静态文件服务、公共工具方法。
具体业务逻辑在 handlers_*.py 中。
"""

import os
import json
from http.server import BaseHTTPRequestHandler
from typing import Any, Optional

# ── 处理器模块（延迟导入） ──
_handlers = None


from lib.api import routes as api_routes  # PY4-A 渐进路由表（表优先，未命中回退本文件分支）


class _HandlerStub:
    """缺失 handler 模块时的占位，避免整站 HTTP 不可用。"""

    def __init__(self, module_name: str):
        self._module_name = module_name

    def __getattr__(self, name: str):
        def _missing(handler, *args, **kwargs):
            handler._send_json(
                {
                    "error": "handler_unavailable",
                    "module": self._module_name,
                    "handler": name,
                },
                503,
            )

        return _missing


def _load_handler_module(module_name: str):
    import importlib

    try:
        return importlib.import_module(f".{module_name}", __package__)
    except ImportError:
        return _HandlerStub(module_name)


def _get_handlers():
    global _handlers
    if _handlers is None:
        _handlers = {
            "inbox": _load_handler_module("handlers_inbox"),
            "system": _load_handler_module("handlers_system"),
            "tasks": _load_handler_module("handlers_tasks"),
            "internal_llm": _load_handler_module("handlers_internal_llm"),
            "gates": _load_handler_module("handlers_gates"),
            "intake": _load_handler_module("handlers_intake"),
            "workflows": _load_handler_module("handlers_workflows"),
            "attachments": _load_handler_module("handlers_attachments"),
            "step_result": _load_handler_module("handlers_step_result"),
            "settings": _load_handler_module("handlers_settings"),
            "lifecycle": _load_handler_module("handlers_lifecycle"),
            "drill": _load_handler_module("handlers_drill"),
            "a2a": _load_handler_module("handlers_a2a"),
            "device": _load_handler_module("handlers_device"),
        }
    return _handlers



class MailbusAPIHandler(BaseHTTPRequestHandler):
    """HTTP API 请求处理器 — 路由分发中心"""

    data_dir = ""
    agents = {}
    agent_types = {}
    auth_token: Optional[str] = None
    require_api_auth: bool = False
    exempt_cidrs: list[str] = []
    bulletin_permit = []
    bulletin_authors = {}
    bulletin_file = ""
    permission_file = ""

    # ── 认证 ────────────────────────────────────────────────────────────

    def _client_is_loopback(self) -> bool:
        """本机（含 Docker/WSL 网桥 + 用户豁免白名单）视为本地请求。"""
        from lib.application.mailbus_token import _is_local
        try:
            addr = (self.client_address[0] or "").strip().lower()
        except Exception:
            return False
        return _is_local(addr, extra_cidrs=self.exempt_cidrs)

    def _check_auth(self, *, write: bool = False) -> bool:
        """Read: token optional unless require_api_auth; presented token must match.
        Write: 默认需要有效 Token（含本机）；仅 config.auth.allow_write_without_token + CIDR 可免。
        """
        # 跨层解耦：api→adapter 通过 composition 拿服务（2026-09 治理）
        from lib.composition import message_zh

        if not write:
            if not self.auth_token:
                return True
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer ") and auth[7:] == self.auth_token:
                return True
            if self.headers.get("X-API-Key") == self.auth_token:
                return True
            # Default cockpit UX: reads work without Bearer unless require_api_auth
            if not auth and not getattr(self, "require_api_auth", False):
                return True
            self._send_json({
                "error": "unauthorized",
                "error_code": "unauthorized",
                "message_zh": message_zh("unauthorized"),
            }, 401)
            return False

        from lib.application.mailbus_token import authorize_write, client_context_from_handler, live_auth_config
        from lib.domain.types import AuthDecision

        ctx = client_context_from_handler(self)
        extra = {}
        if getattr(self, "exempt_cidrs", None):
            extra["exempt_cidrs"] = list(self.exempt_cidrs)
        decision = authorize_write(
            self.data_dir,
            ctx,
            config=live_auth_config(self.data_dir, extra=extra),
        )
        if decision == AuthDecision.ALLOW:
            return True
        self._send_json({
            "error": "unauthorized",
            "error_code": "unauthorized",
            "message_zh": message_zh("unauthorized"),
            "hint": "写操作需要 Authorization: Bearer <mailbus_api_token>；可在配置合页填写。开启 allow_write_without_token 后仅 CIDR 白名单可免 Token。",
        }, 401)
        return False



    # ── 公共工具 ────────────────────────────────────────────────────────

    def _cors_origin(self) -> Optional[str]:
        from lib.infra.cors import pick_cors_origin
        from lib.infra.utils import json_read

        cfg = {}
        try:
            cfg = json_read(os.path.join(self.data_dir or "", "config.json"), {})
        except Exception:
            cfg = {}
        return pick_cors_origin(self.headers.get("Origin", ""), cfg)

    def _apply_cors_headers(self) -> None:
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Credentials", "true")

    def _send_json(self, data: dict, status: int = 200):
        # Wave4: error responses always carry error_code + message_zh
        if status >= 400 and isinstance(data, dict):
            payload = dict(data)
            if "error_code" not in payload:
                raw = payload.get("error") or payload.get("status") or "fatal"
                payload["error_code"] = str(raw)
            if "message_zh" not in payload:
                # 跨层解耦：api→adapter 通过 composition 拿服务
                from lib.composition import message_zh

                code = str(payload.get("error_code") or "fatal")
                detail = str(payload.get("error") or payload.get("detail") or code)
                payload["message_zh"] = message_zh(code, detail)
            data = payload
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._apply_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_api_error(
        self,
        code: str,
        status: int = 400,
        *,
        detail: str = "",
        **extra: Any,
    ) -> None:
        """Prefer structured error_code + message_zh (Wave4)."""
        # 跨层解耦：api→adapter 通过 composition 拿服务（2026-09 治理）
        from lib.composition import message_zh

        payload = {
            "error": detail or code,
            "error_code": code,
            "message_zh": message_zh(code, detail or code),
        }
        if extra:
            payload.update(extra)
        self._send_json(payload, status)

    def _send_sse_start(self, status: int = 200, *, http_status: Optional[int] = None):
        """开始 SSE 响应。

        ``http_status`` 是 A2A 流式的显式状态码入口（handlers_a2a 按 RPC
        结果状态发首帧），与 ``status`` 等价但保留原调用点的关键字形态。
        """
        self.send_response(http_status if http_status is not None else status)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        # 防反代缓冲（与 device/chat 侧 _begin_sse 一致）
        self.send_header("X-Accel-Buffering", "no")
        self._apply_cors_headers()
        self.end_headers()

    def _send_sse_jsonrpc(self, rpc_id, result: dict, *, error: Optional[dict] = None):
        doc: dict = {"jsonrpc": "2.0", "id": rpc_id}
        if error:
            doc["error"] = error
        else:
            doc["result"] = result
        payload = json.dumps(doc, ensure_ascii=False)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _send_sse_comment(self, comment: str = "keepalive"):
        """SSE comment 行保活（不触发客户端 data 事件）。"""
        self.wfile.write(f": {comment}\n\n".encode("utf-8"))
        self.wfile.flush()

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
        from lib.infra.constants import MAILBUS_DOCS_ROOT, MAILBUS_ROOT

        legacy = path.lstrip("/").startswith("legacy")
        filename = "index.html" if path in ("", "/", "/legacy", "/legacy/") else path.lstrip("/")
        if filename.startswith("legacy/"):
            filename = filename[len("legacy/") :] or "index.html"
            legacy = True

        candidates = []
        from lib.infra.constants import REPO_ROOT as _REPO_ROOT  # v1.2: web 在仓库根(实现共享), 不在 shared/
        web_dist = os.path.join(str(_REPO_ROOT), "web", "dist")
        web_public = os.path.join(str(_REPO_ROOT), "web", "public")
        docs_dir = str(MAILBUS_DOCS_ROOT)
        if legacy:
            # Escape hatch: docs/ 侧栏舰队 HUD
            candidates.append(os.path.join(docs_dir, filename if filename != "index.html" else "index.html"))
        else:
            # Product SoT: React 舷窗舰桥 (玻璃 + 星体穿越)
            candidates.append(os.path.join(web_dist, filename))
            candidates.append(os.path.join(web_public, filename))
            candidates.append(os.path.join(docs_dir, "dist", filename))

        for abs_path in candidates:
            abs_path = os.path.normpath(abs_path)
            try:
                with open(abs_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", self._guess_mime(filename))
                self._apply_cors_headers()
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(content)
                return True
            except (OSError, IOError):
                continue
        # SPA fallback: deep links (e.g. /inbox) → web/dist/index.html
        if not legacy and os.path.isdir(web_dist):
            spa_index = os.path.join(web_dist, "index.html")
            try:
                with open(spa_index, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._apply_cors_headers()
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(content)
                return True
            except (OSError, IOError):
                pass
        try:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"static not found")
        except OSError:
            pass
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
        path = self._read_path()
        # SPA/static boot without token; API still authenticated when token configured
        is_device_route = path == "/api/device/chat" or path.startswith("/api/device/chat/")
        needs_api_auth = (path.startswith("/api/") or path.startswith("/a2a/")) and not is_device_route
        if needs_api_auth and not self._check_auth():
            return
        if api_routes.dispatch(self, "GET", path):
            return
        h = _get_handlers()

        if path == "/api/settings/section/services/probe":
            self._send_json({"error": "method_not_allowed", "use": "POST"}, 405)
        elif path.startswith("/api/settings/compose-files/"):
            rel = path[len("/api/settings/compose-files/"):].lstrip("/")
            if rel:
                h["settings"].handle_compose_file_get(self, rel)
            else:
                h["settings"].handle_compose_files_list(self)
        elif path.startswith("/api/a2a/rpc/"):
            agent_id = path[len("/api/a2a/rpc/"):].strip("/")
            if agent_id:
                self._send_json({"error": "method_not_allowed", "use": "POST"}, 405)
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path.startswith("/api/tasks/"):
            # 路由表已覆盖 /api/tasks、/api/tasks/{id}、/api/tasks/{id}/fsm
            # （GET）；此处只保留路由表未覆盖的边界路径。
            rest = path[len("/api/tasks/"):]
            if rest.endswith("/fsm"):
                # 空 id 的退化路径（/api/tasks//fsm）→ 列表视图
                h["tasks"].handle_tasks(self)
            elif "/fsm/" in rest:
                parts = rest.split("/fsm/", 1)
                tid, sub = parts[0], parts[1].split("/")[0]
                if tid and sub in ("rollback", "skip", "cancel", "pause", "priority", "approve-plan", "approve-join", "accept", "continue"):
                    self._send_json({"error": "method_not_allowed", "use": "POST"}, 405)
                elif tid:
                    h["tasks"].handle_task_fsm_get(self, tid)
                else:
                    h["tasks"].handle_tasks(self)
            elif rest:
                h["tasks"].handle_task_get(self, rest)
            else:
                h["tasks"].handle_tasks(self)

        elif path.startswith("/api/device/chat/"):
            ticket_id = path[len("/api/device/chat/"):].strip("/")
            if ticket_id:
                h["device"].handle_device_ticket(self, ticket_id)
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path.startswith("/api/inbox/"):
            # 路由表已覆盖 GET /api/inbox/{agent}（单段）；此处兜底多段路径
            h["inbox"].handle_inbox(self, path[len("/api/inbox/"):])
        elif path.startswith("/api/agent-avatar/"):
            rest = path[len("/api/agent-avatar/"):].strip("/")
            parts = rest.split("/", 1)
            agent = parts[0] if parts else ""
            kind = parts[1] if len(parts) > 1 else "portrait"
            if agent:
                h["system"].handle_agent_avatar(self, agent, kind)
            else:
                self._send_json({"error": "agent required"}, 400)
        elif path.startswith("/api/report-content/"):
            fname = path[len("/api/report-content/"):]
            h["system"].handle_report_content(self, fname)
        elif path in ("", "/"):
            self._serve_static("/")
        elif path == "/index.html":
            self._serve_static("/")
        elif path == "/reviews":
            self._serve_static("reviews.html")
            self._serve_static("/")
        elif path == "/ping-test":
            self._send_json({
                "version": "v2.0.0",
                "agents": len(self.agents),
            })
        elif not self._serve_static(path):
            self._send_json({"error": "not_found", "path": path}, 404)

    # ── HTTP POST 路由 ─────────────────────────────────────────────────

    def do_PATCH(self):
        self.do_POST()

    def do_POST(self):
        path = self._read_path()
        if path == "/api/device/chat":
            # 设备桥走独立设备 token 鉴权，不经 mailbus API token
            h = _get_handlers()
            h["device"].handle_device_chat(self)
            return
        if path == "/api/device/task":
            h = _get_handlers()
            h["device"].handle_device_task(self)
            return
        if path in ("/metis/agent/api/sse", "/agent/api/sse"):
            # 灵珠/Rokid 眼镜上游走独立 AK 鉴权，不经 mailbus API token
            # funnel 的 /metis/ 前缀会剥离，实际到站路径为 /agent/api/sse
            h = _get_handlers()
            h["device"].handle_metis_sse(self)
            return
        if not self._check_auth(write=True):
            return
        if api_routes.dispatch(self, self.command or "POST", path):
            return
        h = _get_handlers()

        if path.startswith("/api/settings/compose-files/"):
            rel = path[len("/api/settings/compose-files/"):].lstrip("/")
            if rel:
                h["settings"].handle_compose_file_put(self, rel)
            else:
                self._send_json({"error": "path required"}, 400)
        else:
            self._send_json({"error": "not_found"}, 404)

    # ── CORS ───────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(200)
        self._apply_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key, X-Mailbus-Device-Token, Accept")
        self.end_headers()

