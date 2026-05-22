"""ziyan-mailbus HTTP API

提供 RESTful API 供 Web 看板或其他工具读取 mailbus 状态。"""
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

from .models import Inbox
from .utils import json_read, resolve_paths, _now_iso
from .tracker import TaskTracker
from .heartbeat import load_status as load_heartbeat
from .alerter import get_recent_alerts


class MailbusAPIHandler(BaseHTTPRequestHandler):
    """HTTP API 处理器"""

    data_dir = ""
    agents = {}
    agent_types = {}

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _read_path(self):
        return self.path.split("?")[0].rstrip("/")

    def do_GET(self):
        path = self._read_path()

        if path == "/api/status":
            self._handle_status()
        elif path == "/api/agents":
            self._handle_agents()
        elif path == "/api/tasks":
            self._handle_tasks()
        elif path == "/api/heartbeat":
            self._handle_heartbeat()
        elif path == "/api/alerts":
            self._handle_alerts()
        elif path.startswith("/api/inbox/"):
            agent = path[len("/api/inbox/"):]
            self._handle_inbox(agent)
        elif path.startswith("/api/agent-profile/"):
            agent = path[len("/api/agent-profile/"):]
            self._handle_agent_profile(agent)
        elif path == "/api/config":
            self._handle_config()
        elif path == "/" or path == "":
            self._send_json({
                "service": "ziyan-mailbus",
                "version": "2.4.0",
                "endpoints": [
                    "GET /api/status      — 总线概要状态",
                    "GET /api/agents       — Agent 列表",
                    "GET /api/tasks        — 任务追踪",
                    "GET /api/heartbeat    — 心跳状态",
                    "GET /api/alerts       — 告警历史",
                    "GET /api/inbox/<name> — 指定 Agent 的 inbox",
                    "GET /api/config       — 当前配置",
                ]
            })
        else:
            self._send_json({"error": "not_found", "path": path}, 404)

    def _handle_status(self):
        """总线概要状态"""
        total_messages = 0
        unread_count = 0
        agent_statuses = {}
        for name in self.agents:
            paths = resolve_paths(self.data_dir)
            inbox_file = f"{paths['inbox']}/{name}/inbox.json"
            data = json_read(inbox_file, {})
            if data:
                msgs = data.get("messages", [])
                total_messages += len(msgs)
                if data.get("has_unread"):
                    for m in msgs:
                        if isinstance(m, dict) and m.get("status") == "pending":
                            unread_count += 1
            agent_statuses[name] = {
                "messages": len(data.get("messages", [])) if data else 0,
                "has_unread": data.get("has_unread", False) if data else False,
                "type": self.agents[name].get("type", "?"),
                "role": self.agents[name].get("role", ""),
            }
        self._send_json({
            "service": "ziyan-mailbus",
            "agents": len(self.agents),
            "total_messages": total_messages,
            "pending_messages": unread_count,
            "agent_statuses": agent_statuses,
            "timestamp": _now_iso(),
        })

    def _handle_agents(self):
        """Agent 列表及配置"""
        detail = {}
        for name, cfg in self.agents.items():
            detail[name] = {
                "name": cfg.get("name", name),
                "role": cfg.get("role", ""),
                "type": cfg.get("type", "none"),
                "models": cfg.get("models", []),
            }
        self._send_json({"agents": detail})

    def _handle_tasks(self):
        """任务追踪列表"""
        tracker = TaskTracker(self.data_dir)
        tasks = tracker.list_all()
        self._send_json({"tasks": tasks, "count": len(tasks)})

    def _handle_heartbeat(self):
        """心跳状态（仅返回缓存，?force=1 时触发一轮检测）"""
        from lib.heartbeat import load_status, heartbeat_scan as _hb_scan
        from urllib.parse import urlparse, parse_qs

        qs = parse_qs(urlparse(self.path).query)
        force = qs.get("force", [""])[0] == "1"

        if force:
            import threading
            t = threading.Thread(target=_hb_scan, args=(self.agents, self.agent_types, self.data_dir),
                                 kwargs={"config": {"agents": self.agents, "agent_types": self.agent_types},
                                          "interval": 0, "full_health_interval": 0}, daemon=True)
            t.start()
            t.join(timeout=15)

        hb = load_status(self.data_dir)
        self._send_json(hb)

    def _handle_alerts(self):
        """告警历史"""
        alerts = get_recent_alerts(self.data_dir, limit=50)
        self._send_json({"alerts": alerts, "count": len(alerts)})

    def _handle_inbox(self, agent: str):
        """指定 Agent 的 inbox 内容"""
        if agent not in self.agents:
            self._send_json({"error": f"agent '{agent}' not found"}, 404)
            return
        paths = resolve_paths(self.data_dir)
        inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
        data = json_read(inbox_file, {})
        if not data:
            self._send_json({"agent": agent, "messages": [], "has_unread": False})
            return
        # 只返回最近 50 条消息的内容摘要
        msgs = data.get("messages", [])
        summary = []
        for m in msgs[-50:]:
            if isinstance(m, dict):
                summary.append({
                    "id": m.get("id", ""),
                    "from": m.get("from", ""),
                    "type": m.get("type", ""),
                    "content_preview": m.get("content", "")[:100],
                    "status": m.get("status", ""),
                    "created_at": m.get("created_at", ""),
                })
        self._send_json({
            "agent": agent,
            "has_unread": data.get("has_unread", False),
            "message_count": len(msgs),
            "messages": summary,
        })

    def _handle_config(self):
        """当前配置（去掉敏感路径信息）"""
        safe = {
            "project": "ziyan-mailbus",
            "version": "2.4.0",
            "dashboard_refresh_seconds": 0,
            "agents": {},
            "agent_types": {},
        }
        # 从 config.json 读 dashboard_refresh_seconds
        config_path = os.path.join(self.data_dir, "config.json")
        raw = json_read(config_path, {})
        if raw and "dashboard_refresh_seconds" in raw:
            safe["dashboard_refresh_seconds"] = raw["dashboard_refresh_seconds"]
        for name, cfg in self.agents.items():
            safe["agents"][name] = {
                "name": cfg.get("name", name),
                "role": cfg.get("role", ""),
                "type": cfg.get("type", "none"),
                "models": cfg.get("models", []),
            }
        for name, cfg in self.agent_types.items():
            if name == "models":
                safe["agent_types"]["models"] = cfg
            else:
                safe["agent_types"][name] = {
                    "description": cfg.get("description", ""),
                }
        self._send_json(safe)

    def _handle_agent_profile(self, agent: str):
        """Agent 详情：从 config.profile_paths 读取身份文件 + 扫描技能"""
        profile = {
            "agent": agent,
            "identity": None,
            "soul": None,
            "skills": [],
            "config": self.agents.get(agent, {}),
        }
        cfg = self.agents.get(agent, {})
        paths = cfg.get("profile_paths", {})

        # 读身份文件
        identity_path = paths.get("identity", "")
        if identity_path and os.path.isfile(identity_path):
            try:
                with open(identity_path, "r", encoding="utf-8", errors="replace") as f:
                    profile["identity"] = f.read(2000)[:1000]
            except Exception:
                pass

        # 读 soul 文件
        soul_path = paths.get("soul", "")
        if soul_path and os.path.isfile(soul_path):
            try:
                with open(soul_path, "r", encoding="utf-8", errors="replace") as f:
                    profile["soul"] = f.read(2000)[:1000]
            except Exception:
                pass

        # 扫描技能目录
        skill_dirs = paths.get("skills_dirs", [])
        all_skills = []
        for sd in skill_dirs:
            if os.path.isdir(sd):
                for entry in sorted(os.listdir(sd)):
                    skill_path = os.path.join(sd, entry)
                    if os.path.isdir(skill_path) and os.path.isfile(os.path.join(skill_path, "SKILL.md")):
                        all_skills.append(entry)
                        if len(all_skills) >= 20:
                            break
                if len(all_skills) >= 20:
                    break
        profile["skills"] = all_skills

        self._send_json(profile)

    def log_message(self, format, *args):
        # 静默日志
        pass


def serve(data_dir: str, agents: dict, agent_types: dict,
          host: str = "127.0.0.1", port: int = 9812):
    """启动 HTTP API 服务"""
    MailbusAPIHandler.data_dir = data_dir
    MailbusAPIHandler.agents = agents
    MailbusAPIHandler.agent_types = agent_types

    server = HTTPServer((host, port), MailbusAPIHandler)
    print(f"📡 mailbus API 服务已启动: http://{host}:{port}")
    print(f"   端点: /api/status /api/agents /api/tasks /api/heartbeat /api/alerts /api/inbox/<name>")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")
        server.server_close()
