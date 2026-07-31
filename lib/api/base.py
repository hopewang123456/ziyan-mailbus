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
        }
    return _handlers



class MailbusAPIHandler(BaseHTTPRequestHandler):
    """HTTP API 请求处理器 — 路由分发中心"""

    data_dir = ""
    agents = {}
    agent_types = {}
    auth_token: Optional[str] = None
    require_api_auth: bool = False
    bulletin_permit = []
    bulletin_authors = {}
    bulletin_file = ""
    permission_file = ""

    # ── 认证 ────────────────────────────────────────────────────────────

    def _client_is_loopback(self) -> bool:
        try:
            addr = (self.client_address[0] or "").strip().lower()
        except Exception:
            return False
        if addr.startswith("::ffff:"):
            addr = addr.split("::ffff:", 1)[-1]
        return addr in ("127.0.0.1", "::1", "localhost")

    def _check_auth(self, *, write: bool = False) -> bool:
        """Read: legacy token-if-configured. Write: localhost free; remote requires token."""
        from lib.locale.errors_zh import message_zh

        if not write:
            if not self.auth_token:
                return True
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer ") and auth[7:] == self.auth_token:
                return True
            if self.headers.get("X-API-Key") == self.auth_token:
                return True
            self._send_json({
                "error": "unauthorized",
                "error_code": "unauthorized",
                "message_zh": message_zh("unauthorized"),
            }, 401)
            return False

        from lib.application.mailbus_token import authorize_write, client_context_from_handler
        from lib.domain.types import AuthDecision

        ctx = client_context_from_handler(self)
        decision = authorize_write(self.data_dir, ctx)
        if decision == AuthDecision.ALLOW:
            return True
        self._send_json({
            "error": "unauthorized",
            "error_code": "unauthorized",
            "message_zh": message_zh("unauthorized"),
            "hint": "本机可免 token；跨机写操作需 Authorization: Bearer <mailbus_api_token>",
        }, 401)
        return False



    # ── 公共工具 ────────────────────────────────────────────────────────

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_sse_start(self, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
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
        from lib.constants import MAILBUS_DOCS_ROOT, MAILBUS_ROOT

        legacy = path.lstrip("/").startswith("legacy")
        filename = "index.html" if path in ("", "/", "/legacy", "/legacy/") else path.lstrip("/")
        if filename.startswith("legacy/"):
            filename = filename[len("legacy/") :] or "index.html"
            legacy = True

        candidates = []
        web_dist = os.path.join(str(MAILBUS_ROOT), "web", "dist")
        docs_dir = str(MAILBUS_DOCS_ROOT)
        if legacy:
            candidates.append(os.path.join(docs_dir, filename if filename != "index.html" else "index.html"))
        else:
            candidates.append(os.path.join(web_dist, filename))
            candidates.append(os.path.join(docs_dir, "dist", filename))
            candidates.append(os.path.join(docs_dir, filename))

        for abs_path in candidates:
            abs_path = os.path.normpath(abs_path)
            try:
                with open(abs_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", self._guess_mime(filename))
                self.send_header("Access-Control-Allow-Origin", "*")
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
                self.send_header("Access-Control-Allow-Origin", "*")
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
        if not self._check_auth():
            return
        path = self._read_path()
        h = _get_handlers()

        routes = {
            "/api/status": lambda: h["system"].handle_status(self),
            "/api/agents": lambda: h["system"].handle_agents(self),
            "/api/frameworks": lambda: h["system"].handle_frameworks(self),
            "/api/tasks": lambda: h["tasks"].handle_tasks(self),
            "/api/tasks/audit/stats/trend": lambda: h["tasks"].handle_task_audit_trend(self),
            "/api/tasks/audit/stats": lambda: h["tasks"].handle_task_audit_stats(self),
            "/api/tasks/audit/pending": lambda: h["tasks"].handle_task_audit_pending(self),
            "/api/heartbeat": lambda: h["system"].handle_heartbeat(self),
            "/api/alerts": lambda: h["system"].handle_alerts(self),
            "/api/config": lambda: h["system"].handle_config(self),
            "/api/stats": lambda: h["system"].handle_stats(self),
            "/api/launch": lambda: h["system"].handle_list_launchable(self),
            "/api/bulletin": lambda: h["tasks"].handle_bulletin(self),
            "/api/bulletin/permit": lambda: self._send_json({"permit": self.bulletin_permit}),
            "/api/permission": lambda: h["tasks"].handle_permission(self),
            "/api/reports": lambda: h["system"].handle_reports(self),
            "/api/patrol-reports": lambda: h["system"].handle_patrol_reports(self),
            "/api/reviews": lambda: h["system"].handle_code_reviews(self),
            "/api/reviews/projects": lambda: h["system"].handle_code_reviews_projects(self),
            "/api/replies": lambda: h["inbox"].handle_replies(self),
            "/api/skill-usage": lambda: h["tasks"].handle_skill_usage(self),
            "/api/skill-use": lambda: h["tasks"].handle_skill_use(self),
            "/api/templates": lambda: h["system"].handle_templates(self),
            "/api/external-tools": lambda: h["system"].handle_external_tools(self),
            "/api/clinic/tools": lambda: h["system"].handle_clinic_tools(self),
            "/api/doctor": lambda: h["system"].handle_doctor(self),
            "/api/locale/errors": lambda: h["system"].handle_locale_errors(self),
            "/api/workload": lambda: h["system"].handle_workload(self),
            "/api/send-msg": lambda: h["inbox"].handle_send_msg(self),
            "/api/internal-llm/status": lambda: h["internal_llm"].handle_internal_llm_status(self),
            "/api/internal-llm/health": lambda: h["internal_llm"].handle_internal_llm_health(self),
            "/api/workflows": lambda: h["workflows"].handle_workflows_list(self),
            "/api/intake": lambda: h["intake"].handle_intake_list(self),
            "/api/settings/sections": lambda: h["settings"].handle_settings_sections(self),
            "/api/settings/env": lambda: h["settings"].handle_settings_env_get(self),
            "/api/settings/integrations": lambda: h["settings"].handle_integrations(self),
            "/api/discover": lambda: h["lifecycle"].handle_discover(self),
            "/api/align": lambda: h["lifecycle"].handle_align(self),
            "/api/agents/active": lambda: h["lifecycle"].handle_active_agents(self),
            "/api/chain/budget": lambda: h["lifecycle"].handle_chain_budget(self),
            "/api/config/mailbus-token": lambda: h["lifecycle"].handle_mailbus_token(self),
        }

        if path in routes:
            routes[path]()
        elif path.startswith("/api/workflows/"):
            wf_id = path[len("/api/workflows/"):].strip("/")
            if wf_id:
                h["workflows"].handle_workflow_get(self, wf_id)
            else:
                h["workflows"].handle_workflows_list(self)
        elif path.startswith("/api/intake/"):
            rest = path[len("/api/intake/"):].strip("/")
            parts = rest.split("/")
            if len(parts) == 1 and parts[0]:
                h["intake"].handle_intake_get(self, parts[0])
            elif len(parts) == 2 and parts[0] and parts[1] == "tasks":
                h["intake"].handle_intake_tasks(self, parts[0])
            elif len(parts) == 2 and parts[0] and parts[1] == "spawn":
                self._send_json({"error": "method_not_allowed", "use": "POST"}, 405)
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path.startswith("/api/settings/section/"):
            section = path[len("/api/settings/section/"):].strip("/")
            if section == "services/probe":
                self._send_json({"error": "method_not_allowed", "use": "POST"}, 405)
            elif section:
                h["settings"].handle_settings_section_get(self, section)
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path.startswith("/api/human-queue"):
            h["tasks"].handle_human_queue(self)
        elif path == "/api/a2a/agent-cards":
            h["a2a"].handle_a2a_agent_card_list(self)
        elif path == "/api/a2a/protocol":
            h["a2a"].handle_a2a_protocol_status(self)
        elif path.startswith("/api/a2a/agent-card/"):
            agent_id = path[len("/api/a2a/agent-card/"):].strip("/")
            if agent_id:
                h["a2a"].handle_a2a_agent_card_get(self, agent_id)
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path.startswith("/api/a2a/rpc/"):
            agent_id = path[len("/api/a2a/rpc/"):].strip("/")
            if agent_id:
                self._send_json({"error": "method_not_allowed", "use": "POST"}, 405)
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path.startswith("/api/tasks/"):
            rest = path[len("/api/tasks/"):]
            if rest.endswith("/fsm"):
                tid = rest[:-4].rstrip("/")
                if tid:
                    h["tasks"].handle_task_fsm_get(self, tid)
                else:
                    h["tasks"].handle_tasks(self)
            elif "/fsm/" in rest:
                parts = rest.split("/fsm/", 1)
                tid, sub = parts[0], parts[1].split("/")[0]
                if tid and sub in ("rollback", "skip", "cancel", "pause", "priority", "approve-plan", "accept", "continue"):
                    self._send_json({"error": "method_not_allowed", "use": "POST"}, 405)
                elif tid:
                    h["tasks"].handle_task_fsm_get(self, tid)
                else:
                    h["tasks"].handle_tasks(self)
            elif rest:
                h["tasks"].handle_task_get(self, rest)
            else:
                h["tasks"].handle_tasks(self)
        
        elif path.startswith("/api/inbox/"):
            h["inbox"].handle_inbox(self, path[len("/api/inbox/"):])
        elif path.startswith("/api/agent-profile/"):
            h["system"].handle_agent_profile(self, path[len("/api/agent-profile/"):])
        elif path.startswith("/api/harness-reports/"):
            sha = path[len("/api/harness-reports/"):].strip("/")
            if sha:
                h["system"].handle_harness_report(self, sha)
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path.startswith("/api/report-content/"):
            fname = path[len("/api/report-content/"):]
            h["system"].handle_report_content(self, fname)
        elif path.startswith("/api/ping/"):
            h["system"].handle_ping(self, path[len("/api/ping/"):])
        elif path.startswith("/api/reviews/"):
            fname = path[len("/api/reviews/"):]
            h["system"].handle_code_reviews_detail(self, fname)
        elif path.startswith("/api/search"):
            h["system"].handle_search(self)
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

    def do_POST(self):
        if not self._check_auth(write=True):
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
        elif path == "/api/tasks/create":
            h["tasks"].handle_task_create(self)
        elif path == "/api/tasks/update":
            h["tasks"].handle_task_update(self)
        elif path == "/api/tasks/audit":
            h["tasks"].handle_task_audit(self)
        elif path == "/api/intake/spawn-analyze":
            h["intake"].handle_intake_spawn_analyze(self)
        elif path.startswith("/api/intake/") and path.endswith("/spawn"):
            rest = path[len("/api/intake/"):].rstrip("/")
            intake_id = rest[: -len("/spawn")].strip("/")
            if intake_id:
                h["intake"].handle_intake_spawn(self, intake_id)
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path.startswith("/api/intake/") and "/gates/" in path:
            rest = path[len("/api/intake/"):]
            parts = rest.split("/")
            if len(parts) >= 4 and parts[1] == "gates" and parts[3] in ("approve", "deny"):
                if parts[3] == "approve":
                    h["intake"].handle_intake_gate_approve(self, parts[0], parts[2])
                else:
                    h["intake"].handle_intake_gate_deny(self, parts[0], parts[2])
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path.startswith("/api/tasks/") and "/gates/" in path:
            rest = path[len("/api/tasks/"):]
            parts = rest.split("/")
            if len(parts) >= 4 and parts[1] == "gates" and parts[3] in ("approve", "deny"):
                h["gates"].handle_gate_approve(self, parts[0], parts[2]) if parts[3] == "approve" else h["gates"].handle_gate_deny(self, parts[0], parts[2])
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path.startswith("/api/human-queue/") and path.endswith("/resolve"):
            item_id = path[len("/api/human-queue/"): -len("/resolve")].strip("/")
            if item_id:
                h["tasks"].handle_human_queue_resolve(self, item_id)
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path.startswith("/api/tasks/") and "/fsm/" in path:
            rest = path[len("/api/tasks/"):]
            parts = rest.split("/fsm/", 1)
            tid, action = parts[0], parts[1].split("/")[0]
            h["tasks"].handle_task_fsm_action(self, tid, action)
        elif path == "/api/send-msg":
            h["inbox"].handle_send_msg(self)
        elif path == "/api/internal-llm/dry-run":
            h["internal_llm"].handle_internal_llm_dry_run(self)
        elif path == "/api/internal-llm/rebuild-rag":
            h["internal_llm"].handle_internal_llm_rebuild_rag(self)
        elif path == "/api/attachments/upload":
            h["attachments"].handle_attachment_upload(self)
        elif path.startswith("/api/agents/") and path.endswith("/step-result"):
            agent_id = path[len("/api/agents/"): -len("/step-result")].strip("/")
            if agent_id:
                h["step_result"].handle_agent_step_result(self, agent_id)
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path == "/api/clinic/run":
            h["system"].handle_clinic_run(self)
        elif path == "/api/drill/video-publish":
            h["drill"].handle_drill_video_publish(self)
        elif path == "/api/agents/recruit":
            h["system"].handle_agent_recruit(self)
        elif path.startswith("/api/workflows/") and path.endswith("/delete"):
            wf_id = path[len("/api/workflows/"): -len("/delete")].strip("/")
            h["workflows"].handle_workflow_delete(self, wf_id)
        elif path.startswith("/api/workflows/"):
            wf_id = path[len("/api/workflows/"):].strip("/")
            if wf_id and wf_id not in ("delete",):
                h["workflows"].handle_workflow_save(self, wf_id)
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path == "/api/settings/env":
            h["settings"].handle_settings_env_patch(self)
        elif path == "/api/align":
            h["lifecycle"].handle_align(self)
        elif path == "/api/chain/budget":
            h["lifecycle"].handle_chain_budget(self)
        elif path in ("/api/config/mailbus-token", "/api/config/mailbus-token/rotate"):
            h["lifecycle"].handle_mailbus_token(self)
        elif path.startswith("/api/frameworks/") and path.endswith("/enable"):
            fid = path[len("/api/frameworks/"): -len("/enable")].strip("/")
            h["lifecycle"].handle_framework_enable(self, fid)
        elif path.startswith("/api/frameworks/") and path.endswith("/disable"):
            fid = path[len("/api/frameworks/"): -len("/disable")].strip("/")
            h["lifecycle"].handle_framework_disable(self, fid)
        elif path.startswith("/api/agents/") and path.endswith("/enable"):
            aid = path[len("/api/agents/"): -len("/enable")].strip("/")
            h["lifecycle"].handle_role_enable(self, aid)
        elif path.startswith("/api/settings/section/"):
            section = path[len("/api/settings/section/"):].strip("/")
            if section == "services/probe":
                h["settings"].handle_settings_services_probe(self)
            elif section:
                h["settings"].handle_settings_section_patch(self, section)
            else:
                self._send_json({"error": "not_found"}, 404)
        elif path == "/api/a2a/tasks":
            h["a2a"].handle_a2a_tasks_create(self)
        elif path.startswith("/api/a2a/rpc/"):
            agent_id = path[len("/api/a2a/rpc/"):].strip("/")
            if agent_id:
                h["a2a"].handle_a2a_rpc(self, agent_id)
            else:
                self._send_json({"error": "not_found"}, 404)
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

