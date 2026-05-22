"""ziyan-mailbus 心跳检测 & 健康监控

定时对所有 Agent 执行心跳 ping，检测在线状态。
同时监控 AgentMemory 连接、API Key 有效性、inbox 积压、磁盘空间。

离线 Agent 不进推送重试，直接写错误队列。"""
import os
import subprocess
import time
import shutil
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

from .utils import json_read, json_write, resolve_paths, _now_iso


HEARTBEAT_STATUS_FILE = "heartbeat.json"

# 默认心跳配置
DEFAULT_PING_INTERVAL = 300       # 5 分钟 ping 一次
DEFAULT_MISSED_LIMIT = 3          # 连续 N 次无响应标记 offline
DEFAULT_PING_TIMEOUT = 10         # 每次 ping 超时（秒）
DEFAULT_INBOX_WARN_LIMIT = 50     # inbox 消息数超过此值告警
DEFAULT_DISK_WARN_MB = 500        # store 目录大小超过此值告警


def get_heartbeat_path(data_dir: str) -> str:
    return os.path.join(data_dir, HEARTBEAT_STATUS_FILE)


def load_status(data_dir: str) -> dict:
    return json_read(get_heartbeat_path(data_dir), {"agents": {}, "health": {}})


def save_status(data_dir: str, status: dict):
    json_write(get_heartbeat_path(data_dir), status)


def is_online(data_dir: str, agent_name: str) -> bool:
    """查询 agent 是否在线"""
    status = load_status(data_dir)
    agent = status.get("agents", {}).get(agent_name, {})
    if not agent:
        return True
    return agent.get("status") == "online"


# ── 健康检查项 ───────────────────────────────────────────────────

def check_agentmemory(url: str = "http://localhost:3111") -> dict:
    """检查 AgentMemory 是否可连接"""
    try:
        import urllib.request
        req = urllib.request.Request(f"{url}/agentmemory/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return {"status": "healthy", "latency_ms": resp.headers.get("X-Response-Time", "?")}
        return {"status": "error", "detail": f"HTTP {resp.status}"}
    except Exception as e:
        return {"status": "unreachable", "detail": str(e)[:80]}


def check_inbox_size(data_dir: str, agents: dict, warn_limit: int = DEFAULT_INBOX_WARN_LIMIT) -> list:
    """检查各 Agent inbox 消息数量"""
    warnings = []
    paths = resolve_paths(data_dir)
    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        data = json_read(inbox_file, {})
        msgs = data.get("messages", []) if data else []
        count = len(msgs)
        if count > warn_limit:
            warnings.append({"agent": name, "count": count, "level": "warn" if count < warn_limit * 2 else "critical"})
    return warnings


def check_disk_space(data_dir: str, warn_mb: int = DEFAULT_DISK_WARN_MB) -> Optional[dict]:
    """检查 store 目录磁盘占用"""
    try:
        total_bytes = 0
        for dirpath, dirnames, filenames in os.walk(data_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total_bytes += os.path.getsize(fp)
                except OSError:
                    pass
        total_mb = total_bytes / (1024 * 1024)
        if total_mb > warn_mb:
            return {"status": "warn", "size_mb": round(total_mb, 1), "warn_mb": warn_mb}
        return {"status": "ok", "size_mb": round(total_mb, 1)}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:80]}


def ping_agent(agent_cfg: dict, agent_types: dict, ping_timeout: int = DEFAULT_PING_TIMEOUT) -> bool:
    """对单个 agent 执行心跳 ping"""
    atype = agent_cfg.get("type", "none")
    tmpl = agent_types.get(atype, {}).get("heartbeat", "")

    if not tmpl:
        push_tmpl = agent_types.get(atype, {}).get("push", "")
        if not push_tmpl:
            return False
        ping_cmd = push_tmpl
        ping_cmd = ping_cmd.replace("PROFILE", agent_cfg.get("profile", ""))
        ping_cmd = ping_cmd.replace("AGENT", agent_cfg.get("agent", ""))
        ping_cmd = ping_cmd.replace("MODEL", "")
        ping_cmd = ping_cmd.replace("--model MODEL", "").replace("-m MODEL", "")
        ping_cmd = ping_cmd.replace("'MSG'", "'ping'")
        ping_cmd = ping_cmd.strip()
    else:
        ping_cmd = tmpl
        ping_cmd = ping_cmd.replace("PROFILE", agent_cfg.get("profile", ""))

    if not ping_cmd:
        return False

    try:
        result = subprocess.run(
            ping_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=ping_timeout,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


# ── 主检测流程 ─────────────────────────────────────────────────────

def health_scan(data_dir: str, agents: dict) -> dict:
    """
    全面健康检查（不依赖 agent ping，只检查基础设施）。

    返回: {
        "agentmemory": {"status": "healthy"|"unreachable", ...},
        "disk": {"status": "ok"|"warn", "size_mb": ...},
        "inbox_warnings": [{"agent": "...", "count": N, "level": "warn"|"critical"}, ...],
        "timestamp": "..."
    }
    """
    health = {}
    health["agentmemory"] = check_agentmemory()
    health["disk"] = check_disk_space(data_dir)
    health["inbox_warnings"] = check_inbox_size(data_dir, agents)
    health["timestamp"] = _now_iso()
    return health


def heartbeat_scan(agents: dict, agent_types: dict, data_dir: str,
                   interval: int = DEFAULT_PING_INTERVAL,
                   missed_limit: int = DEFAULT_MISSED_LIMIT,
                   full_health_interval: int = 600) -> list:
    """
    执行一轮心跳检测 + 健康检查（健康检查间隔较长）。

    返回状态变化通知列表：[{agent, old_status, new_status}, ...]
    """
    status = load_status(data_dir)
    agent_states = status.setdefault("agents", {})
    health_state = status.setdefault("health", {})
    changes = []
    now_ts = _now_iso()

    # ── Agent 心跳检测 ──
    for name, cfg in agents.items():
        agent_state = agent_states.setdefault(name, {
            "status": "online",
            "last_heartbeat": "",
            "missed_pings": 0,
        })

        last_hb = agent_state.get("last_heartbeat", "")
        if last_hb:
            try:
                last_dt = datetime.strptime(last_hb, "%Y-%m-%dT%H:%M:%S%z")
                now_dt = datetime.now(timezone(timedelta(hours=8)))
                if (now_dt - last_dt).total_seconds() < interval:
                    continue
            except (ValueError, TypeError):
                pass

        online = ping_agent(cfg, agent_types)
        agent_state["last_heartbeat"] = now_ts

        if online:
            old_status = agent_state["status"]
            agent_state["status"] = "online"
            agent_state["missed_pings"] = 0
            if old_status != "online":
                changes.append({"agent": name, "old_status": old_status, "new_status": "online"})
        else:
            agent_state["missed_pings"] += 1
            if agent_state["missed_pings"] >= missed_limit:
                old_status = agent_state["status"]
                agent_state["status"] = "offline"
                if old_status != "offline":
                    changes.append({"agent": name, "old_status": old_status, "new_status": "offline"})

    # ── 基础设施健康检查（full_health_interval 间隔执行）──
    last_health_check = health_state.get("last_check", "")
    do_health_check = True
    if last_health_check:
        try:
            last_dt = datetime.strptime(last_health_check, "%Y-%m-%dT%H:%M:%S%z")
            now_dt = datetime.now(timezone(timedelta(hours=8)))
            if (now_dt - last_dt).total_seconds() < full_health_interval:
                do_health_check = False
        except (ValueError, TypeError):
            pass

    if do_health_check:
        health = health_scan(data_dir, dict(agents))
        health_state["last_check"] = now_ts
        health_state["agentmemory"] = health["agentmemory"]
        health_state["disk"] = health["disk"]
        health_state["inbox_warnings"] = health["inbox_warnings"]

        # 健康状态变化也加入通知
        am_status = health["agentmemory"].get("status", "")
        prev_am = health_state.get("agentmemory", {}).get("status", "")
        if am_status != prev_am and prev_am:
            changes.append({
                "agent": "agentmemory",
                "old_status": prev_am,
                "new_status": am_status,
                "type": "health"
            })

    save_status(data_dir, status)
    return changes
