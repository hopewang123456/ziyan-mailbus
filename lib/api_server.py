"""ziyan-mailbus HTTP API

提供 RESTful API 供 Web 看板或其他工具读取 mailbus 状态。"""
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional

from .models import Inbox
from .utils import json_read, json_write, resolve_paths, _now_iso
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

    def _serve_static(self, path: str) -> bool:
        """尝试返回 docs/ 目录下的静态文件"""
        # 安全：只允许 docs/ 下的文件，防路径穿越
        if ".." in path or "~" in path:
            return False
        docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
        if path in ("", "/"):
            filename = "index.html"
        else:
            filename = path.lstrip("/")
        abs_path = os.path.normpath(os.path.join(docs_dir, filename))
        if not abs_path.startswith(os.path.normpath(docs_dir)):
            return False
        if not os.path.isfile(abs_path):
            return False
        try:
            with open(abs_path, "rb") as f:
                content = f.read()
            content_type = "text/html" if filename.endswith(".html") else \
                           "application/javascript" if filename.endswith(".js") else \
                           "text/css" if filename.endswith(".css") else \
                           "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Access-Control-Allow-Origin", "*")
            # 对 HTML 注入 cache buster
            if filename.endswith(".html"):
                import time
                buster = str(int(time.time()))
                content = content.replace(
                    b'loadAll();',
                    b'// cb=' + buster.encode() + b'\nloadAll();',
                )
            self.end_headers()
            self.wfile.write(content)
            return True
        except Exception:
            return False

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
        elif path.startswith("/api/ping/"):
            agent = path[len("/api/ping/"):]
            self._handle_ping(agent)
        elif path == "/api/config":
            self._handle_config()
        elif path == "/api/launch":
            # GET → 显示可启动的 agent 列表
            self._list_launchable()
        elif path == "/api/bulletin":
            self._handle_bulletin()
        elif path == "/api/bulletin/permit":
            self._send_json({"permit": self.bulletin_permit})
        elif path == "/api/permission":
            self._handle_permission()
        elif path == "/api/reports":
            self._handle_reports()
        elif path == "/api/replies":
            self._handle_replies()
        elif path == "/api/skill-usage":
            self._handle_skill_usage()
        elif path == "/" or path == "":
            self._serve_static("/")
        elif path == "/index.html":
            self._serve_static("/")
        elif path == "/ping-test":
            # 调试端点：确认版本
            self._send_json({"version": "v2.0.0", "file_size": os.path.getsize(
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "platform.html")
            ), "agents": len(self.agents)})
        else:
            # 尝试返回静态文件
            if not self._serve_static(path):
                self._send_json({"error": "not_found", "path": path}, 404)

    def do_POST(self):
        path = self._read_path()

        if path == "/api/launch":
            self._handle_launch()
        elif path == "/api/bulletin/post":
            self._handle_bulletin_post()
        elif path == "/api/bulletin/permit":
            self._handle_bulletin_permit()
        elif path == "/api/permission":
            self._handle_permission()
        elif path.startswith("/api/mark-read/"):
            agent = path[len("/api/mark-read/"):]
            self._handle_mark_read(agent)
        else:
            self._send_json({"error": "not_found"}, 404)

    # ── 公告板配置 ──
    bulletin_permit = []      # 有权限发公告的 agent name 列表
    bulletin_authors = {}     # 作者显示名映射
    bulletin_file = ""        # bulletin.json 路径，由 serve() 设置
    permission_file = ""      # permission.json 路径，由 serve() 设置

    def _load_bulletin(self) -> dict:
        """读取公告板"""
        try:
            return json_read(self.bulletin_file, {"bulletins": []})
        except Exception:
            return {"bulletins": []}

    def _save_bulletin(self, data: dict):
        """写入公告板"""
        json_write(self.bulletin_file, data)

    def _read_post_body(self):
        "读取 POST 请求体"
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            body = self.rfile.read(content_length)
            try:
                return json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {}
        return {}

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
                "active_messages": len([m for m in data.get("messages", []) if isinstance(m, dict) and m.get("status") != "archived"]) if data else 0,
                "has_unread": data.get("has_unread", False) if data else False,
                "unread_count": len([m for m in data.get("messages", []) if isinstance(m, dict) and m.get("status") != "acknowledged" and m.get("status") != "archived" and m.get("type") != "system"]) if data else 0,
                "pending_count": len([m for m in data.get("messages", []) if isinstance(m, dict) and m.get("status") == "pending"]) if data else 0,
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
        from lib.heartbeat import load_status_nolock, heartbeat_scan as _hb_scan
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

        hb = load_status_nolock(self.data_dir)
        self._send_json(hb)

    def _handle_alerts(self):
        """告警历史"""
        alerts = get_recent_alerts(self.data_dir, limit=50)
        self._send_json({"alerts": alerts, "count": len(alerts)})

    def _handle_inbox(self, agent: str):
        """指定 Agent 的 inbox 内容（排除已归档消息）"""
        if agent not in self.agents:
            self._send_json({"error": f"agent '{agent}' not found"}, 404)
            return
        paths = resolve_paths(self.data_dir)
        inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
        data = json_read(inbox_file, {})
        if not data:
            self._send_json({"agent": agent, "messages": [], "has_unread": False})
            return
        msgs = data.get("messages", [])
        # 只返回未归档的消息
        active = [m for m in msgs if isinstance(m, dict) and m.get("status") != "archived"]
        summary = []
        for m in active:
            if isinstance(m, dict):
                summary.append({
                    "id": m.get("id", ""),
                    "from": m.get("from", ""),
                    "to": m.get("to", ""),
                    "type": m.get("type", ""),
                    "content_preview": m.get("content", "")[:100],
                    "status": m.get("status", ""),
                    "read": m.get("read", False),
                    "created_at": m.get("created_at", ""),
                })
        self._send_json({
            "agent": agent,
            "has_unread": data.get("has_unread", False),
            "total_messages": len(msgs),
            "active_messages": len(active),
            "messages": summary,
        })

    def _handle_bulletin(self):
        """GET /api/bulletin → 返回公告列表"""
        b = self._load_bulletin()
        self._send_json(b)

    def _handle_bulletin_post(self):
        """POST /api/bulletin/post → 发公告（需权限）"""
        body = self._read_post_body()
        sender = body.get("from", "")
        content = body.get("content", "").strip()
        title = body.get("title", "").strip()

        if sender not in self.bulletin_permit:
            self._send_json({"error": f"'{sender}' 无发布公告权限"}, 403)
            return
        if not content:
            self._send_json({"error": "公告内容不能为空"}, 400)
            return

        bulletin = {
            "id": f"b{int(__import__('time').time() * 1000)}{sender[:3]}",
            "from": sender,
            "from_name": self.bulletin_authors.get(sender) or self.agents.get(sender, {}).get("name", sender),
            "title": title or "公告",
            "content": content,
            "created_at": _now_iso(),
        }
        b = self._load_bulletin()
        b.setdefault("bulletins", []).insert(0, bulletin)
        self._save_bulletin(b)
        self._send_json({"status": "ok", "bulletin": bulletin})

    def _handle_bulletin_permit(self):
        """POST /api/bulletin/permit → 更新公告权限列表"""
        body = self._read_post_body()
        permit = body.get("permit", [])
        if not isinstance(permit, list):
            self._send_json({"error": "permit 必须是数组"}, 400)
            return
        # 写入 config.json
        config_path = os.path.join(self.data_dir, "config.json")
        raw = json_read(config_path, {})
        raw["bulletin_permit"] = permit
        json_write(config_path, raw)
        self.bulletin_permit = permit
        self._send_json({"status": "ok", "permit": permit})

    def _handle_mark_read(self, agent: str):
        """POST /api/mark-read/<agent> → 标记指定 agent 的 inbox 全部已读"""
        if agent not in self.agents:
            self._send_json({"error": f"agent '{agent}' not found"}, 404)
            return
        paths = resolve_paths(self.data_dir)
        inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
        data = json_read(inbox_file, {})
        if not data:
            self._send_json({"status": "ok", "marked": 0})
            return
        # 标记所有非 system 消息为 acknowledged（agent 已读）
        changed = 0
        for m in data.get("messages", []):
            if isinstance(m, dict) and m.get("type") != "system" and m.get("status") != "acknowledged" and m.get("status") != "archived":
                m["status"] = "acknowledged"
                m["read_at"] = _now_iso()
                changed += 1
        data["has_unread"] = any(
            isinstance(m, dict) and m.get("type") != "system" and m.get("status") != "acknowledged" and m.get("status") != "archived"
            for m in data.get("messages", [])
        )
        json_write(inbox_file, data)
        self._send_json({"status": "ok", "agent": agent, "marked": changed})

    def _handle_permission(self):
        """GET /api/permission → 返回权限配置"""
        if self.command == "GET":
            perm = json_read(self.permission_file, {})
            self._send_json({"permissions": perm})
        elif self.command == "POST":
            body = self._read_post_body()
            permissions = body.get("permissions", {})
            if not isinstance(permissions, dict):
                self._send_json({"error": "permissions 必须是对象"}, 400)
                return
            json_write(self.permission_file, permissions)
            # 保存一份到 self 供前端实时使用
            self.permissions = permissions
            self._send_json({"status": "ok", "permissions": permissions})

    def _handle_reports(self):
        """GET /api/reports → 返回审查报告列表"""
        reports_dir = os.path.join(self.data_dir, "reports")
        reports = []
        if os.path.isdir(reports_dir):
            for fname in sorted(os.listdir(reports_dir), reverse=True):
                if fname.endswith(".md"):
                    fpath = os.path.join(reports_dir, fname)
                    try:
                        size = os.path.getsize(fpath)
                        mtime = os.path.getmtime(fpath)
                        import datetime
                        mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                        # 取报告前 200 字作为摘要
                        preview = ""
                        with open(fpath, encoding="utf-8") as f:
                            preview = f.read()[:300]
                        reports.append({
                            "file": fname,
                            "size": size,
                            "time": mtime_str,
                            "content": preview,
                        })
                    except Exception:
                        pass
                    if len(reports) >= 30:
                        break
        self._send_json({"reports": reports, "count": len(reports)})

    def _handle_replies(self):
        """GET /api/replies → 返回所有 agent 的回复记录"""
        replies_dir = os.path.join(self.data_dir, "replies")
        replies = []
        if os.path.isdir(replies_dir):
            for fname in sorted(os.listdir(replies_dir), reverse=True):
                if fname.endswith(".json"):
                    fpath = os.path.join(replies_dir, fname)
                    try:
                        with open(fpath, encoding="utf-8") as f:
                            data = json.load(f)
                        replies.append(data)
                    except Exception:
                        pass
                    if len(replies) >= 50:
                        break
        self._send_json({"replies": replies, "count": len(replies)})

    def _handle_skill_usage(self):
        """GET /api/skill-usage → 聚合所有 agent 的 skill 使用情况"""
        import os, json
        profiles = {
            "lingzhao": "/mnt/e/hermes-data/.hermes/skills/.usage.json",
            "lingxi": "/mnt/e/hermes-data/.hermes/profiles/lingxi/skills/.usage.json",
        }
        merged = {}
        for agent, path in profiles.items():
            if os.path.isfile(path):
                try:
                    with open(path) as f:
                        data = json.load(f)
                    for skill, rec in data.items():
                        if skill not in merged:
                            merged[skill] = {"agents": {}}
                        merged[skill]["agents"][agent] = {
                            "use_count": rec.get("use_count", 0),
                            "view_count": rec.get("view_count", 0),
                            "last_used": (rec.get("last_used_at") or "")[:16],
                            "state": rec.get("state", "active"),
                        }
                        # 汇总统计
                        merged[skill]["total_use"] = sum(
                            a.get("use_count", 0) for a in merged[skill]["agents"].values()
                        )
                        merged[skill]["total_view"] = sum(
                            a.get("view_count", 0) for a in merged[skill]["agents"].values()
                        )
                        merged[skill]["last_used"] = max(
                            (a.get("last_used", "") for a in merged[skill]["agents"].values()),
                            default="",
                        )
                except Exception:
                    pass
        
        # 按使用次数排序
        sorted_skills = sorted(
            merged.items(),
            key=lambda x: -(x[1].get("total_use", 0) or 0),
        )
        self._send_json({
            "skills": [{"name": n, **d} for n, d in sorted_skills],
            "total_skills": len(sorted_skills),
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

    def _list_launchable(self):
        """返回所有可启动的 agent 列表，含支持的模式"""
        agents = {}
        for name, cfg in self.agents.items():
            atype = cfg.get("type", "none")
            # 所有 agent 都支持 browser 和 cli 两种模式
            launch_modes = ["browser", "cli"]
            has_browser = cfg.get("launch", {}).get("has_browser", True)
            agents[name] = {
                "name": cfg.get("name", name),
                "type": atype,
                "launch_modes": launch_modes,
                "has_browser": has_browser,
                "models": cfg.get("models", []),
            }
        self._send_json({"agents": agents})

    def _handle_launch(self):
        """POST /api/launch → 启动指定 agent 的 CLI/浏览器窗口
           body: {"agent": "<name>", "mode": "browser"|"cli"}
        """
        body = self._read_post_body()
        agent = body.get("agent", "")
        mode = body.get("mode", "browser")

        if not agent or agent not in self.agents:
            self._send_json({"error": f"agent '{agent}' not found"}, 404)
            return

        cfg = self.agents[agent]
        atype = cfg.get("type", "none")
        agent_name = cfg.get("name", agent)

        # 调用 launch-agent.sh（第二个参数传 mode）
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "launch-agent.sh")
        if not os.path.isfile(script_path):
            self._send_json({"error": "launch script not found"}, 500)
            return

        import subprocess, shlex
        try:
            result = subprocess.run(
                ["bash", script_path, agent, mode],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                self._send_json({"status": "ok", "agent": agent, "message": f"Launched {agent_name}"})
            else:
                self._send_json({"status": "error", "agent": agent,
                                 "error": result.stderr.strip() or result.stdout.strip()}, 500)
        except subprocess.TimeoutExpired:
            self._send_json({"status": "timeout", "agent": agent}, 500)
        except Exception as e:
            self._send_json({"status": "error", "error": str(e)}, 500)

    def _update_heartbeat_cache(self, agent: str, status: str):
        """更新心跳缓存"""
        try:
            from .heartbeat import load_status_nolock, save_status
            hb_cache = load_status_nolock(self.data_dir)
            agent_state = hb_cache.setdefault("agents", {}).setdefault(agent, {})
            agent_state["status"] = status
            agent_state["last_heartbeat"] = __import__("datetime").datetime.now(
                __import__("datetime").timezone(__import__("datetime").timedelta(hours=8))
            ).isoformat()
            if status == "online":
                agent_state["missed_pings"] = 0
            save_status(self.data_dir, hb_cache)
        except Exception:
            pass

    def _handle_ping(self, agent: str):
        """GET /api/ping/<agent> → 对 agent 做一次即时 ping 检测，unreachable 时尝试重启"""
        from urllib.parse import urlparse, parse_qs

        # 特殊处理：AgentMemory
        if agent == "agentmemory":
            from .heartbeat import check_agentmemory
            import subprocess, time, os, shutil

            # 先找到 agentmemory 命令
            am_cmd = shutil.which("agentmemory") or os.path.expanduser("~/.npm-global/bin/agentmemory")
            if not os.path.isfile(am_cmd):
                self._send_json({"agent": "agentmemory", "status": "error", "detail": "agentmemory 命令未找到"}, 500)
                return

            # 先 kill 旧的 agentmemory 进程
            subprocess.Popen(["pkill", "-f", "agentmemory"], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.Popen(["pkill", "-f", "iii.*engine"], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)

            # 重新启动
            try:
                logfile = "/tmp/agentmemory-restart.log"
                subprocess.Popen(
                    ["bash", "-c", f"cd ~ && nohup {am_cmd} >{logfile} 2>&1 &"],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                # 等待端口就绪（最多 15 秒）
                for i in range(15):
                    time.sleep(1)
                    result = check_agentmemory()
                    if result["status"] == "healthy":
                        # 强制更新心跳缓存
                        try:
                            from .heartbeat import load_status_nolock, save_status
                            hb_cache = load_status_nolock(self.data_dir)
                            hb_cache.setdefault("health", {})
                            hb_cache["health"]["agentmemory"] = result
                            hb_cache["health"]["last_check"] = __import__("datetime").datetime.now(
                                __import__("datetime").timezone(__import__("datetime").timedelta(hours=8))
                            ).isoformat()
                            save_status(self.data_dir, hb_cache)
                        except Exception:
                            pass
                        self._send_json({
                            "agent": "agentmemory",
                            "status": "healthy",
                            "detail": f"重启成功（第{i+1}秒响应）",
                        })
                        return
                # 超时
                result = check_agentmemory()
                self._send_json({
                    "agent": "agentmemory",
                    "status": result["status"],
                    "detail": f"启动超时，请检查 /tmp/agentmemory-restart.log",
                })
            except Exception as e:
                self._send_json({"agent": "agentmemory", "status": "error", "detail": str(e)[:80]}, 500)
            return

        # 普通 agent
        if agent not in self.agents:
            self._send_json({"error": f"agent '{agent}' not found"}, 404)
            return

        cfg = self.agents[agent]
        atype = cfg.get("type", "none")

        # OpenClaw 类型：先检测 gateway，gateway 挂了就不需要 ping agent 了
        if atype == "openclaw":
            import subprocess, time

            # 从 agent 配置获取 gateway port（默认 18789）
            gw_config = cfg.get("launch", {}).get("browser", {})
            gw_port = gw_config.get("gateway_port", 18789)
            gw_url = f"http://localhost:{gw_port}"

            # 开启 gateway 的命令
            gw_cmd = gw_config.get("start_command", "")
            if not gw_cmd:
                gw_cmd = f"export PATH=$HOME/.npm-global/bin:$HOME/.local/bin:$PATH && openclaw gateway run --auth none --port {gw_port} --force"

            gw_ok = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", gw_url],
                capture_output=True, text=True, timeout=5,
            )
            if gw_ok.stdout.strip() != "200":
                # 尝试启动 gateway
                try:
                    subprocess.Popen(
                        ["bash", "-c", f"{gw_cmd} >/tmp/openclaw-gw-{agent}.log 2>&1 &"],
                        start_new_session=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    # 等几秒看 gateway 能不能起来
                    for i in range(10):
                        time.sleep(1)
                        r = subprocess.run(
                            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", gw_url],
                            capture_output=True, text=True, timeout=3,
                        )
                        if r.stdout.strip() == "200":
                            # 更新心跳缓存：gateway 已启动
                            self._update_heartbeat_cache(agent, "online")
                            self._send_json({
                                "agent": agent,
                                "status": "online",
                                "detail": f"Gateway 启动成功（第{i+1}秒响应），agent 已恢复",
                            })
                            return
                    # gateway 启动超时
                    try:
                        log_content = open(f"/tmp/openclaw-gw-{agent}.log").read()[-300:]
                    except Exception:
                        log_content = "无日志"
                    self._send_json({
                        "agent": agent,
                        "status": "gateway_down",
                        "detail": f"OpenClaw Gateway ({gw_url}) 启动失败。日志: {log_content}",
                    }, 500)
                    return
                except Exception as e:
                    self._send_json({
                        "agent": agent,
                        "status": "gateway_down",
                        "detail": f"Gateway 启动异常: {str(e)[:80]}",
                    }, 500)
                    return

        from .heartbeat import ping_agent
        online = ping_agent(cfg, self.agent_types, ping_timeout=10)

        if not online:
            # 离线 → 尝试重启
            try:
                script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "launch-agent.sh")
                if os.path.isfile(script_path):
                    import subprocess
                    subprocess.Popen(
                        ["bash", script_path, agent],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    # 等几秒再检测一次
                    import time
                    time.sleep(5)
                    online = ping_agent(cfg, self.agent_types, ping_timeout=10)
            except Exception:
                pass

        # 无论在线离线，都强制更新心跳缓存（让页面刷新后不再显示旧状态）
        self._update_heartbeat_cache(agent, "online" if online else "offline")

        self._send_json({
            "agent": agent,
            "status": "online" if online else "offline",
            "detail": "",
        })

    def log_message(self, format, *args):
        # 静默日志
        pass


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTPServer — 每个请求在独立线程处理，不阻塞其他请求"""
    daemon_threads = True


def serve(data_dir: str, agents: dict, agent_types: dict,
          host: str = "127.0.0.1", port: int = 9812):
    """启动 HTTP API 服务"""
    MailbusAPIHandler.data_dir = data_dir
    MailbusAPIHandler.agents = agents
    MailbusAPIHandler.agent_types = agent_types

    # 读取公告板配置
    config_path = os.path.join(data_dir, "config.json")
    raw = json_read(config_path, {})
    MailbusAPIHandler.bulletin_permit = raw.get("bulletin_permit", [])
    MailbusAPIHandler.bulletin_authors = raw.get("bulletin_authors", {})
    MailbusAPIHandler.bulletin_file = os.path.join(data_dir, "bulletin.json")
    MailbusAPIHandler.permission_file = os.path.join(data_dir, "permission.json")
    MailbusAPIHandler.permissions = json_read(MailbusAPIHandler.permission_file, {})

    server = ThreadingHTTPServer((host, port), MailbusAPIHandler)
    print(f"📡 mailbus API 服务已启动: http://{host}:{port}")
    print(f"   端点: /api/status /api/agents /api/tasks /api/heartbeat /api/alerts /api/inbox/<name>")
    print(f"   公告板: {len(MailbusAPIHandler.bulletin_permit)} 人可发公告")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")
        server.server_close()
