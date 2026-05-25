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
        if data:
            inbox = Inbox.from_dict(data)
            unread += sum(1 for m in inbox.messages if inbox.msg_field(m, "status") == "pending")
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
            "type": cfg.get("type", "?"),
            "role": cfg.get("role", ""),
            "models": cfg.get("models", []),
            "webhook_url": cfg.get("webhook_url", ""),
        }
    handler._send_json(result)


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
    """GET /api/agent-profile/<agent> — agent 详细信息"""
    cfg = handler.agents.get(agent)
    if not cfg:
        handler._send_json({"error": "not found"}, 404)
        return
    paths = resolve_paths(handler.data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    data = json_read(inbox_file, {})
    msg_count = len(data.get("messages", [])) if data else 0
    unread = 0
    if data:
        inbox = Inbox.from_dict(data)
        for m in inbox.messages:
            if inbox.msg_field(m, "status") == "pending":
                unread += 1
    hb_data = load_heartbeat(handler.data_dir)
    agent_hb = (hb_data.get("agents", {}) or {}).get(agent, {}) if hb_data else {}
    handler._send_json({
        "name": agent, "config": cfg, "messages": msg_count, "unread": unread,
        "heartbeat": agent_hb,
    })


def handle_ping(handler, agent: str):
    """GET /api/ping/<agent> — ping agent 检查在线状态"""
    from lib.heartbeat import is_online
    online = is_online(handler.data_dir, agent)
    handler._send_json({"agent": agent, "online": online})


def handle_list_launchable(handler):
    """GET /api/launch — 列出可启动的 agent"""
    launchable = []
    for name, cfg in handler.agents.items():
        if cfg.get("type") not in ("none", ""):
            launchable.append({"name": name, "type": cfg.get("type", "?"), "role": cfg.get("role", "")})
    handler._send_json({"launchable": launchable})


def handle_launch(handler):
    """POST /api/launch — 启动 agent"""
    body = handler._read_post_body()
    agent = body.get("agent", "")
    if not agent or agent not in handler.agents:
        handler._send_json({"error": "agent not found"}, 404)
        return
    cfg = handler.agents[agent]
    atype = cfg.get("type", "")

    if atype == "agentmemory":
        _launch_agentmemory(handler)
        return

    launch_scripts = {
        "hermes": ["bash", "-c", f"cd ~ && nohup hermes --profile {cfg.get('profile', 'default')} >/dev/null 2>&1 &"],
        "opencode": ["bash", "-c", "cd /mnt/e/ai_tools/opencode && nohup python3 opencode_gui.py >/dev/null 2>&1 &"],
        "cline": ["bash", "-c", "cd ~ && nohup cline --provider openai-compatible --yolo >/dev/null 2>&1 &"],
    }
    cmd = launch_scripts.get(atype)
    if not cmd:
        handler._send_json({"error": f"不支持启动类型: {atype}"}, 400)
        return
    try:
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        handler._send_json({"agent": agent, "status": "launched", "type": atype})
    except Exception as e:
        handler._send_json({"error": str(e)}, 500)


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

    handler._send_json(safe)
