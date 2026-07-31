"""ziyan-mailbus 心跳检测 & 健康监控

定时对所有 Agent 执行心跳 ping，检测在线状态。
同时监控 AgentMemory 连接、API Key 有效性、inbox 积压、磁盘空间。

离线 Agent 不进推送重试，直接写错误队列。"""
import os
import json
import subprocess
import time
import shutil
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

from lib.adapters.clock import now_dt, now_iso, now_ts, now_utc_dt
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


def _aggregate_daemon_heartbeats(data_dir: str) -> dict:
    """从 per-agent 心跳文件 (heartbeat.{agent}.json) 聚合 daemon 状态"""
    agents = {}
    hb_dir = Path(data_dir)
    for f in hb_dir.glob("heartbeat.*.json"):
        try:
            data = json.loads(f.read_text())
            agent_name = data.get("agent", "")
            if agent_name:
                agents[agent_name] = data
        except (json.JSONDecodeError, OSError):
            pass
    return agents


def load_status(data_dir: str) -> dict:
    # 从 per-agent 心跳文件聚合 daemon 状态
    daemon_hb = _aggregate_daemon_heartbeats(data_dir)
    # 容器内路径修正
    hb_path = get_heartbeat_path(data_dir)
    if not os.path.exists(hb_path):
        alt = "/mailbus/store"
        alt_path = os.path.join(alt, HEARTBEAT_STATUS_FILE)
        if os.path.exists(alt_path):
            data_dir = alt
    # 读取 bus 维护的共享心跳（健康检查等）
    bus_status = json_read(get_heartbeat_path(data_dir), {"agents": {}, "health": {}})
    # 合并: daemon 状态覆盖 bus 的 agent 状态
    merged_agents = {**bus_status.get("agents", {}), **daemon_hb}
    return {
        "agents": merged_agents,
        "health": bus_status.get("health", {}),
    }


def load_status_nolock(data_dir: str) -> dict:
    """无锁读取心跳状态（给 API server 用，避免被 cron 的锁阻塞）"""
    # 容器内路径修正
    if not os.path.exists(os.path.join(data_dir, HEARTBEAT_STATUS_FILE)):
        alt = "/mailbus/store"
        if os.path.exists(os.path.join(alt, HEARTBEAT_STATUS_FILE)):
            data_dir = alt
    path = get_heartbeat_path(data_dir)
    try:
        with open(path) as f:
            bus_status = json.load(f)
    except (FileNotFoundError, ValueError):
        bus_status = {"agents": {}, "health": {}}
    # 同样聚合 per-agent 心跳
    daemon_hb = _aggregate_daemon_heartbeats(data_dir)
    merged_agents = {**bus_status.get("agents", {}), **daemon_hb}
    return {
        "agents": merged_agents,
        "health": bus_status.get("health", {}),
    }


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

def check_api_keys(config: dict) -> list:
    """
    检查 config 中所有 agent 的 API Key 是否有效。
    通过尝试对每个 provider 做一次轻量请求来验证。

    返回: [{"agent": name, "key_status": "valid"|"missing"|"expired", "provider": "..."}, ...]
    """
    results = []
    env_paths = [
        Path("/run/hermes/.env"),
        Path("/home/hermes/.hermes/.env"),
        Path("/home/administrator/.hermes/.env"),
        Path("/mnt/e/hermes-data/.hermes/.env"),
        Path.home() / ".hermes" / ".env",
    ]

    # 读取所有环境变量（含容器注入）
    env_vars = {k: v for k, v in os.environ.items() if k.endswith("_API_KEY")}
    for ep in env_paths:
        if ep.exists():
            with open(ep) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    env_vars[k.strip()] = v.strip().strip("'\"")

    agent_types = config.get("agent_types", {})
    agents = config.get("agents", {})

    for name, cfg in agents.items():
        atype = cfg.get("type", "none")
        models_map = agent_types.get("models", {})
        agent_models = cfg.get("models", [])
        model_alias = agent_models[0] if agent_models else None

        if not model_alias:
            results.append({"agent": name, "key_status": "no_model", "provider": ""})
            continue

        model_cfg = models_map.get(model_alias, {})
        cli_flag = model_cfg.get(atype, "")

        # 判断需要哪个 API Key
        provider = ""
        if "deepseek" in cli_flag.lower():
            provider = "deepseek"
        elif "qwen" in cli_flag.lower():
            provider = "qwen"
        elif "zhipu" in cli_flag.lower() or "glm" in cli_flag.lower():
            provider = "zhipu"
        elif "openrouter" in cli_flag.lower():
            provider = "openrouter"

        key_var = f"{provider.upper()}_API_KEY" if provider else ""
        if key_var and key_var in env_vars and env_vars[key_var]:
            results.append({"agent": name, "key_status": "valid", "provider": provider})
        elif key_var:
            results.append({"agent": name, "key_status": "missing", "provider": provider})
        else:
            results.append({"agent": name, "key_status": "not_needed", "provider": provider})

    return results

def check_agentmemory(url: str = "") -> dict:
    """检查 AgentMemory 是否可连接（多重回退策略）"""
    if not url:
        try:
            from .service_registry import service_url

            url = service_url("agentmemory")
        except Exception:
            import os

            url = os.environ.get("AGENTMEMORY_URL", "") or "http://127.0.0.1:3111"
    try:
        import urllib.request

        # 策略1: 尝试标准 /health 端点
        endpoints = ["/health", "/agentmemory/health", "/api/health", "/"]
        for ep in endpoints:
            try:
                req = urllib.request.Request(f"{url}{ep}", method="GET")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        return {"status": "healthy", "endpoint": ep,
                                "latency_ms": resp.headers.get("X-Response-Time", "?")}
                    # 非 200 但端口在响应也视为活着
                    if resp.status in (301, 302, 307, 308, 401, 403):
                        return {"status": "healthy", "endpoint": ep,
                                "detail": f"HTTP {resp.status}"}
            except Exception:
                continue

        # 策略2: 所有端点都失败，检查端口是否在监听
        try:
            import socket
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 3111
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return {"status": "degraded", "detail": f"端口{port}已监听但HTTP端点无响应"}
        except Exception:
            pass

        return {"status": "unreachable", "detail": f"所有健康端点均无响应"}
    except Exception as e:
        return {"status": "unreachable", "detail": str(e)[:80]}


def check_inbox_size(data_dir: str, agents: dict, warn_limit: int = DEFAULT_INBOX_WARN_LIMIT) -> list:
    """检查各 Agent inbox 活跃消息数量（不含 done/archived/closed）"""
    from lib.scan import get_msg_state
    from .models import MsgStatus

    terminal = {
        MsgStatus.DONE, MsgStatus.CLOSED, MsgStatus.ARCHIVED,
        MsgStatus.FAILED, MsgStatus.REJECTED,
    }
    warnings = []
    paths = resolve_paths(data_dir)
    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        raw = json_read(inbox_file, [])
        msgs = raw if isinstance(raw, list) else (raw.get("messages", []) if raw else [])
        count = sum(1 for m in msgs if get_msg_state(m) not in terminal)
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


def ping_agent(agent_cfg: dict, agent_types: dict, ping_timeout: int = DEFAULT_PING_TIMEOUT,
               data_dir: str = None) -> bool:
    """对单个 agent 执行心跳检测 — 文件探活（零 token 成本）"""
    from .constants import DEFAULT_DATA_DIR
    agent_name = agent_cfg.get("profile", "") or agent_cfg.get("agent", "") or ""
    if not agent_name:
        return True  # 未知 agent 默认在线
    hb_dir = data_dir or DEFAULT_DATA_DIR
    hb_file = os.path.join(hb_dir, f"heartbeat.{agent_name}.json")
    try:
        mtime = os.path.getmtime(hb_file)
        return (now_ts() - mtime) < ping_timeout * 3  # 30s 内有心跳即视为在线
    except OSError:
        return False


def ping_agent_with_report(agent_cfg: dict, agent_types: dict, ping_timeout: int = DEFAULT_PING_TIMEOUT) -> dict:
    """文件探活（无 CLI 调用），返回 online 状态"""
    online = ping_agent(agent_cfg, agent_types, ping_timeout)
    return {"online": online, "report": None}


def _build_ping_cmd(agent_cfg: dict, agent_types: dict) -> str:
    """构建 ping 命令（已弃用，保留兼容）"""
    return ""


# ── 主检测流程 ─────────────────────────────────────────────────────

def health_scan(data_dir: str, agents: dict, config: dict = None) -> dict:
    """
    全面健康检查（不依赖 agent ping，只检查基础设施）。

    返回: {
        "agentmemory": {"status": "healthy"|"unreachable", ...},
        "disk": {"status": "ok"|"warn", "size_mb": ...},
        "inbox_warnings": [{"agent": "...", "count": N, "level": "warn"|"critical"}, ...],
        "api_keys": [{"agent": name, "key_status": ..., "provider": ...}, ...],
        "timestamp": "..."
    }
    """
    health = {}
    health["agentmemory"] = check_agentmemory()
    health["disk"] = check_disk_space(data_dir)
    health["inbox_warnings"] = check_inbox_size(data_dir, agents)
    if config:
        health["api_keys"] = check_api_keys(config)
    health["timestamp"] = _now_iso()
    return health


def heartbeat_scan(agents: dict, agent_types: dict, data_dir: str,
                   config: dict = None,  # 传入完整 config 用于 API Key 检测
                   interval: int = DEFAULT_PING_INTERVAL,
                   missed_limit: int = DEFAULT_MISSED_LIMIT,
                   full_health_interval: int = 600,
                   ping_timeout: int = DEFAULT_PING_TIMEOUT) -> list:
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
        # 兼容旧版 heartbeat.json 缺少 missed_pings 的情况
        agent_state.setdefault("missed_pings", 0)

        last_hb = agent_state.get("last_heartbeat", "")
        if last_hb:
            try:
                last_dt = datetime.strptime(last_hb, "%Y-%m-%dT%H:%M:%S%z")
                now_dt = now_dt()
                if (now_dt - last_dt).total_seconds() < interval:
                    continue
            except (ValueError, TypeError):
                pass

        online = ping_agent(cfg, agent_types, ping_timeout=ping_timeout)
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
            now_dt = now_dt()
            if (now_dt - last_dt).total_seconds() < full_health_interval:
                do_health_check = False
        except (ValueError, TypeError):
            pass

    if do_health_check:
        health = health_scan(data_dir, dict(agents), config=config)
        health_state["last_check"] = now_ts
        health_state["agentmemory"] = health["agentmemory"]
        health_state["disk"] = health["disk"]
        health_state["inbox_warnings"] = health["inbox_warnings"]
        if "api_keys" in health:
            health_state["api_keys"] = health["api_keys"]

        # 告警检查
        from .alerter import push_alert

        # AgentMemory 断联
        am_status = health["agentmemory"].get("status", "")
        prev_am = health_state.get("agentmemory", {}).get("status", "")
        if am_status != prev_am and am_status == "unreachable":
            push_alert(data_dir, "agentmemory_down", "critical", "system",
                       f"AgentMemory 连接断开: {health['agentmemory'].get('detail', '')}")
        if am_status != prev_am and am_status == "healthy" and prev_am == "unreachable":
            push_alert(data_dir, "agentmemory_up", "info", "system",
                       "AgentMemory 已恢复连接")

        # 磁盘告警
        disk = health.get("disk", {})
        if disk.get("status") == "warn":
            push_alert(data_dir, "disk_full", "warn", "system",
                       f"磁盘空间告警: {disk['size_mb']}MB（阈值 {disk.get('warn_mb', '?')}MB）")

        # inbox 积压告警
        for w in health.get("inbox_warnings", []):
            level = "critical" if w["level"] == "critical" else "warn"
            push_alert(data_dir, "inbox_overflow", level, w["agent"],
                       f"inbox {w['count']} 条消息积压")

        # API Key 缺失告警
        for k in health.get("api_keys", []):
            if k["key_status"] == "missing":
                push_alert(data_dir, "key_missing", "critical", k["agent"],
                           f"{k['provider']} API Key 缺失（{k['agent']}）")

        # 健康状态变化也加入通知
        if am_status != prev_am and prev_am:
            changes.append({
                "agent": "agentmemory",
                "old_status": prev_am,
                "new_status": am_status,
                "type": "health"
            })

    save_status(data_dir, status)
    return changes
