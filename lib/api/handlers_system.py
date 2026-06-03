"""
ziyan-mailbus HTTP API — 系统相关路由处理器

处理: /api/status, /api/agents, /api/heartbeat, /api/alerts,
      /api/config, /api/reports, /api/search, /api/templates,
      /api/agent-profile/, /api/ping/, /api/launch
"""

import os
import json
import time
import subprocess
from lib.models import Inbox
from lib.utils import json_read, json_write, resolve_paths
from lib.heartbeat import load_status as load_heartbeat
from lib.alerter import get_recent_alerts


def handle_status(handler):
    """GET /api/status — 总线概要状态"""
    total = 0
    unread = 0
    agent_statuses = {}
    paths = resolve_paths(handler.data_dir)
    for name in handler.agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        data = json_read(inbox_file, {})
        count = len(data.get("messages", [])) if data else 0
        total += count
        if data and "agent" in data:
            try:
                inbox = Inbox.from_dict(data)
                # P4: 统计所有非 terminal 态消息（pending/pushed/acknowledged/processing）
                terminal_states = {"done", "closed", "rejected", "failed", "archived", "sent"}
                unread += sum(1 for m in inbox.messages
                              if (inbox.msg_field(m, "state") or inbox.msg_field(m, "status", ""))
                              not in terminal_states)
            except (KeyError, TypeError):
                pass
        agent_statuses[name] = {
            "active_messages": count,
            "has_unread": data.get("has_unread", False) if data else False,
            "type": handler.agents[name].get("type", "?"),
        }
    handler._send_json({
        "project": "ziyan-mailbus", "agents": len(handler.agents),
        "total_messages": total, "unread_messages": unread,
        "agent_statuses": agent_statuses,
    })


def handle_agents(handler):
    """GET /api/agents — 获取 agent 列表和配置"""
    result = {}
    for name, cfg in handler.agents.items():
        result[name] = {
            "name": cfg.get("name", name),
            "role": cfg.get("role", ""),
            "type": cfg.get("type", "?"),
            "models": cfg.get("models", []),
            "webhook_url": cfg.get("webhook_url", ""),
        }
    handler._send_json({"agents": result})


def handle_heartbeat(handler):
    """GET /api/heartbeat — 心跳状态"""
    hb_data = load_heartbeat(handler.data_dir)
    handler._send_json(hb_data if hb_data else {"status": "unknown"})


def handle_alerts(handler):
    """GET /api/alerts — 告警信息"""
    alerts = get_recent_alerts(handler.data_dir, limit=50)
    handler._send_json({"alerts": alerts})


def handle_config(handler):
    """GET /api/config — 查看总线配置"""
    config_path = f"{handler.data_dir}/config.json"
    config = json_read(config_path, {})
    safe = {k: v for k, v in config.items() if k != "token"}
    handler._send_json(safe)


def _extract_repo_name(fname: str) -> str:
    """从文件名提取仓库名: review-mailbus-20260526.md → mailbus
    旧格式 review-<commit_prefix>-<date>.md → 未知项目"""
    parts = fname.replace(".md", "").split("-")
    if len(parts) >= 3 and parts[0] == "review":
        repo_parts = []
        for p in parts[1:]:
            # 纯数字且>=8位 → 日期戳，停止
            if p.isdigit() and len(p) >= 8:
                break
            # 短 hex（commit hash 前缀）→ 旧格式，返回未知
            if len(p) <= 8 and all(c in "0123456789abcdef" for c in p.lower()):
                return "未知项目（旧报告）"
            repo_parts.append(p)
        if repo_parts:
            return "-".join(repo_parts)
    return "未知项目（旧报告）"


def handle_code_reviews(handler):
    """GET /api/reviews — 返回代码审查报告列表"""
    reports_dir = os.path.join(handler.data_dir, "reports")
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
                    preview = ""
                    with open(fpath, encoding="utf-8") as f:
                        preview = f.read()[:300]
                    repo = _extract_repo_name(fname)
                    reports.append({"file": fname, "repo": repo, "size": size,
                                    "time": mtime_str, "content": preview})
                except Exception:
                    pass
    handler._send_json({"reports": reports, "count": len(reports)})


def handle_code_reviews_projects(handler):
    """GET /api/reviews/projects — 按项目分组的代码审查报告"""
    reports_dir = os.path.join(handler.data_dir, "reports")
    projects = {}
    if os.path.isdir(reports_dir):
        for fname in sorted(os.listdir(reports_dir), reverse=True):
            if fname.endswith(".md"):
                fpath = os.path.join(reports_dir, fname)
                try:
                    repo = _extract_repo_name(fname)
                    mtime = os.path.getmtime(fpath)
                    import datetime
                    mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    projects.setdefault(repo, []).append({
                        "file": fname,
                        "time": mtime_str,
                        "size": os.path.getsize(fpath),
                    })
                except Exception:
                    pass
    for repo in projects:
        projects[repo] = projects[repo][:10]
    handler._send_json({"projects": projects, "count": len(projects)})


def handle_code_reviews_detail(handler, fname: str):
    """GET /api/reviews/<file> — 返回单份代码审查报告"""
    fpath = os.path.join(handler.data_dir, "reports", fname)
    if not os.path.isfile(fpath) or not fname.endswith(".md"):
        handler._send_json({"error": "not found"}, 404)
        return
    try:
        with open(fpath, encoding="utf-8") as f:
            content = f.read()
        # 尝试用 markdown 渲染
        try:
            import markdown
            html = markdown.markdown(content, extensions=["fenced_code", "codehilite"])
        except ImportError:
            html = f"<pre>{content}</pre>"
        handler._send_json({"file": fname, "html": html, "raw": content})
    except Exception as e:
        handler._send_json({"error": str(e)}, 500)


def handle_reports(handler):
    """GET /api/reports — 获取错误报告"""
    import glob
    errors_dir = os.path.join(handler.data_dir, "errors")
    reports = []
    if os.path.isdir(errors_dir):
        for fpath in sorted(glob.glob(f"{errors_dir}/*.jsonl"), reverse=True)[:7]:
            try:
                with open(fpath) as f:
                    lines = f.readlines()
                fname = os.path.basename(fpath)
                entries = []
                for line in lines[-20:]:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
                reports.append({"file": fname, "count": len(lines), "recent": entries})
            except (OSError, IOError):
                pass
    handler._send_json({"reports": reports})


def handle_search(handler):
    """GET /api/search — 消息检索"""
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(handler.path).query)
    query = qs.get("query", [""])[0]
    from_agent = qs.get("from", [""])[0]
    to_agent = qs.get("to", [""])[0]
    msg_type = qs.get("type", [""])[0]
    status = qs.get("status", [""])[0]
    try:
        limit = int(qs.get("limit", ["20"])[0])
    except (ValueError, TypeError):
        limit = 20
    from lib.search import search
    results = search(handler.data_dir, query=query, from_agent=from_agent,
                     to_agent=to_agent, msg_type=msg_type, status=status, limit=limit)
    handler._send_json({"query": query, "total": len(results), "results": results})


def handle_templates(handler):
    """GET /api/templates — agent 类型模板"""
    handler._send_json(handler.agent_types)


def handle_agent_profile(handler, agent: str):
    """GET /api/agent-profile/<agent> — agent 详细信息（含身份/人设/技能）"""
    cfg = handler.agents.get(agent)
    if not cfg:
        handler._send_json({"error": "not found"}, 404)
        return

    profile = {
        "name": agent,
        "config": cfg,
        "identity": None,
        "soul": None,
        "skills": [],
    }

    # 从 profile_paths 读取身份/人设/技能
    paths_cfg = cfg.get("profile_paths", {})
    identity_path = paths_cfg.get("identity", "")
    if identity_path and os.path.isfile(identity_path):
        try:
            with open(identity_path, "r", encoding="utf-8", errors="replace") as f:
                profile["identity"] = f.read(2000)[:1000]
        except Exception:
            pass

    soul_path = paths_cfg.get("soul", "")
    if soul_path and os.path.isfile(soul_path):
        try:
            with open(soul_path, "r", encoding="utf-8", errors="replace") as f:
                profile["soul"] = f.read(2000)[:1000]
        except Exception:
            pass

    skill_dirs = paths_cfg.get("skills_dirs", [])
    all_skills = set()
    for sd in skill_dirs:
        if os.path.isdir(sd):
            try:
                for fname in sorted(os.listdir(sd)):
                    if fname.endswith((".md", ".py", ".sh", ".txt")):
                        all_skills.add(fname.rsplit(".", 1)[0])
            except Exception:
                pass
    profile["skills"] = sorted(all_skills)

    # inbox 统计
    inbox_paths = resolve_paths(handler.data_dir)
    inbox_file = f"{inbox_paths['inbox']}/{agent}/inbox.json"
    data = json_read(inbox_file, {})
    profile["messages"] = len(data.get("messages", [])) if data else 0
    profile["unread"] = 0
    if data:
        inbox = Inbox.from_dict(data)
        for m in inbox.messages:
            if inbox.msg_field(m, "status") == "pending":
                profile["unread"] += 1

    # 心跳
    hb_data = load_heartbeat(handler.data_dir)
    profile["heartbeat"] = (hb_data.get("agents", {}) or {}).get(agent, {}) if hb_data else {}

    handler._send_json(profile)


def handle_ping(handler, agent: str):
    """GET /api/ping/<agent> — ping agent 检查在线状态"""
    from lib.heartbeat import is_online
    online = is_online(handler.data_dir, agent)
    handler._send_json({"agent": agent, "online": online})


def _get_gateway_token() -> str:
    """从 OpenClaw 配置中读取 gateway token
    优先读 ~/.openclaw-data/openclaw.json（新版主配置），
    fallback 到 ~/.openclaw/openclaw.json（旧版）
    """
    candidates = [
        os.path.expanduser("~/.openclaw-data/openclaw.json"),
        os.path.expanduser("~/.openclaw/openclaw.json"),
    ]
    for oc_path in candidates:
        try:
            if os.path.isfile(oc_path):
                with open(oc_path) as f:
                    oc = json.load(f)
                gw = oc.get("gateway", {})
                auth = gw.get("auth", {})
                if auth.get("mode") == "token":
                    return auth.get("token", "")
        except Exception:
            pass
    return ""


def _get_launch_url(handler, agent_name: str) -> str:
    """从 agent 配置中提取浏览器启动 URL（含 gateway token）"""
    cfg = handler.agents.get(agent_name, {})
    launch = cfg.get("launch", {})
    if not launch:
        return ""
    # 合并模板 + agent 覆盖（与 launch-agent.sh 逻辑一致）
    tmpl_name = launch.get("template", "")
    tmpl = handler.agent_types.get("launch_templates", {}).get(tmpl_name, {})
    browser_cfg = dict(tmpl.get("browser", {}))
    browser_cfg.update(launch.get("browser", {}))
    url = browser_cfg.get("url", "")
    port = browser_cfg.get("gateway_port", browser_cfg.get("dashboard_port", ""))
    if url and port:
        url = url.replace("{port}", str(port))
    # 如果 gateway 开启了 token 认证，自动追加到 URL
    token = _get_gateway_token()
    if token:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}token={token}"
    return url


def handle_list_launchable(handler):
    """GET /api/launch — 列出可启动的 agent（含启动模式、has_browser、launch_url 等信息）"""
    result = {}
    for name, cfg in handler.agents.items():
        atype = cfg.get("type", "none")
        launch_modes = ["browser", "cli"]
        has_browser = cfg.get("launch", {}).get("has_browser", True)
        launch_url = _get_launch_url(handler, name)
        result[name] = {
            "name": cfg.get("name", name),
            "type": atype,
            "launch_modes": launch_modes,
            "has_browser": has_browser,
            "launch_url": launch_url,
            "models": cfg.get("models", []),
        }
    handler._send_json({"agents": result})


def handle_launch(handler):
    """POST /api/launch — 通过 launch-agent.sh 启动 agent"""
    body = handler._read_post_body()
    agent = body.get("agent", "")
    mode = body.get("mode", "browser")

    if not agent or agent not in handler.agents:
        handler._send_json({"error": f"agent '{agent}' not found"}, 404)
        return

    # 查找 launch-agent.sh 脚本
    script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "launch-agent.sh")
    if not os.path.isfile(script_path):
        handler._send_json({"error": "launch script not found"}, 500)
        return

    try:
        result = subprocess.run(
            ["bash", script_path, agent, mode],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            handler._send_json({"status": "ok", "agent": agent, "message": f"Launched {agent} ({mode})"})
        else:
            handler._send_json({"status": "error", "agent": agent,
                                "error": result.stderr.strip() or result.stdout.strip()}, 500)
    except subprocess.TimeoutExpired:
        handler._send_json({"status": "timeout", "agent": agent}, 500)
    except Exception as e:
        handler._send_json({"status": "error", "error": str(e)}, 500)


def _launch_agentmemory(handler):
    """启动 AgentMemory 服务"""
    am_path = "/mnt/e/ai_tools/Agent-Reach"
    am_cmd = f"cd {am_path} && python3 -m agentmemory.service"
    if not os.path.isdir(am_path):
        handler._send_json({"error": f"目录不存在: {am_path}"}, 404)
        return
    try:
        subprocess.Popen(["pkill", "-f", "agentmemory"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        logfile = "/tmp/agentmemory-restart.log"
        subprocess.Popen(
            ["bash", "-c", f"cd ~ && nohup {am_cmd} >{logfile} 2>&1 &"],
            start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for i in range(15):
            time.sleep(1)
            result = _check_agentmemory()
            if result.get("status") == "healthy":
                handler._send_json({"agent": "agentmemory", "status": "healthy", "detail": f"重启成功（第{i+1}秒响应）"})
                return
        handler._send_json({"agent": "agentmemory", "status": "timeout", "detail": "15秒内未就绪"})
    except Exception as e:
        handler._send_json({"error": str(e)}, 500)


def _check_agentmemory():
    try:
        from urllib.request import urlopen
        resp = urlopen("http://127.0.0.1:3111/health", timeout=5)
        return {"status": "healthy"} if resp.getcode() == 200 else {"status": "error"}
    except Exception:
        return {"status": "unreachable"}
