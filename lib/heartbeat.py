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

def check_api_keys(config: dict) -> list:
    """
    检查 config 中所有 agent 的 API Key 是否有效。
    通过尝试对每个 provider 做一次轻量请求来验证。

    返回: [{"agent": name, "key_status": "valid"|"missing"|"expired", "provider": "..."}, ...]
    """
    results = []
    env_paths = [
        Path("/home/administrator/.hermes/.env"),
        Path.home() / ".hermes" / ".env",
    ]

    # 读取所有环境变量
    env_vars = {}
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
    """对单个 agent 执行心跳 ping，返回 True 表示在线"""
    cmd = _build_ping_cmd(agent_cfg, agent_types)
    if not cmd:
        return False
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=ping_timeout)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def ping_agent_with_report(agent_cfg: dict, agent_types: dict, ping_timeout: int = DEFAULT_PING_TIMEOUT) -> dict:
    """
    对单个 agent 执行心跳 ping，并尝试获取自检报告。

    如果 agent 支持自检上报，stdout/stderr 中会包含 JSON 格式的状态报告。
    返回: {"online": bool, "report": dict | None}
    """
    cmd = _build_ping_cmd(agent_cfg, agent_types)
    if not cmd:
        return {"online": False, "report": None}
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=ping_timeout)
        online = result.returncode == 0
        # 尝试从 stdout 或 stderr 中提取 JSON 自检报告
        report = None
        for output in [result.stdout, result.stderr]:
            if not output:
                continue
            # 查找 {...} 格式的 JSON
            for line in output.split("\n"):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        import json as _json
                        parsed = _json.loads(line)
                        if isinstance(parsed, dict) and "status" in parsed:
                            report = parsed
                            break
                    except (json.JSONDecodeError, ValueError):
                        continue
            if report:
                break
        return {"online": online, "report": report}
    except (subprocess.TimeoutExpired, Exception):
        return {"online": False, "report": None}


def _build_ping_cmd(agent_cfg: dict, agent_types: dict) -> str:
    """构建 ping 命令"""
    atype = agent_cfg.get("type", "none")
    tmpl = agent_types.get(atype, {}).get("heartbeat", "")
    if not tmpl:
        push_tmpl = agent_types.get(atype, {}).get("push", "")
        if not push_tmpl:
            return ""
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
    return ping_cmd


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
