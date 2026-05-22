"""ziyan-mailbus 心跳检测

定时对所有 Agent 执行心跳 ping，检测在线状态。
离线 Agent 不进推送重试，直接写错误队列。"""
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

from .utils import json_read, json_write, resolve_paths, _now_iso


HEARTBEAT_STATUS_FILE = "heartbeat.json"

# 默认心跳配置
DEFAULT_PING_INTERVAL = 300       # 5 分钟 ping 一次
DEFAULT_MISSED_LIMIT = 3          # 连续 N 次无响应标记 offline
DEFAULT_PING_TIMEOUT = 10         # 每次 ping 超时（秒）


def get_heartbeat_path(data_dir: str) -> str:
    """心跳状态文件路径"""
    return os.path.join(data_dir, HEARTBEAT_STATUS_FILE)


def load_status(data_dir: str) -> dict:
    """加载心跳状态"""
    return json_read(get_heartbeat_path(data_dir), {"agents": {}})


def save_status(data_dir: str, status: dict):
    """保存心跳状态"""
    json_write(get_heartbeat_path(data_dir), status)


def is_online(data_dir: str, agent_name: str) -> bool:
    """查询 agent 是否在线"""
    status = load_status(data_dir)
    agent = status.get("agents", {}).get(agent_name, {})
    if not agent:
        return True  # 无记录默认在线
    return agent.get("status") == "online"


def ping_agent(agent_cfg: dict, agent_types: dict, ping_timeout: int = DEFAULT_PING_TIMEOUT) -> bool:
    """
    对单个 agent 执行心跳 ping。
    返回 True 表示在线。
    """
    atype = agent_cfg.get("type", "none")
    tmpl = agent_types.get(atype, {}).get("heartbeat", "")

    if not tmpl:
        # 无心跳模板 → 使用 push 模板做一个轻量 ping
        push_tmpl = agent_types.get(atype, {}).get("push", "")
        if not push_tmpl:
            return False
        # 用 push 模板发一个简单的 ping 消息
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


def heartbeat_scan(agents: dict, agent_types: dict, data_dir: str,
                   interval: int = DEFAULT_PING_INTERVAL,
                   missed_limit: int = DEFAULT_MISSED_LIMIT) -> list:
    """
    执行一轮心跳检测。

    返回状态变化通知列表：[{agent, old_status, new_status}, ...]
    """
    status = load_status(data_dir)
    agent_states = status.setdefault("agents", {})
    changes = []
    now_ts = _now_iso()

    for name, cfg in agents.items():
        agent_state = agent_states.setdefault(name, {
            "status": "online",
            "last_heartbeat": "",
            "missed_pings": 0,
        })

        last_hb = agent_state.get("last_heartbeat", "")
        # 如果上次心跳到现在不足 interval 秒，跳过
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

    save_status(data_dir, status)
    return changes
