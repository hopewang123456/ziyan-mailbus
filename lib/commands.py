#!/usr/bin/env python3
"""
ziyan-mailbus — 多 Agent 消息总线系统

用法:
  bus.py init [--fresh]              初始化 store（--fresh 从 SoT 重建）
  bus.py scan                        扫描全员 inbox → 推送未读消息
  bus.py send <agent> --msg <内容>    手动发消息
         [--priority urgent] [--from <发件人>] [--type <类型>]
  bus.py broadcast --msg <内容>       发公告板（全员推送）
  bus.py ack --msg-id <ID>           agent 确认收到
  bus.py mark-read --msg-ids <ID,...> agent 标记已读
  bus.py status [--agent <名>] [--failed]  查看消息状态
  bus.py retry [--msg-id <ID>]       重试失败消息
  bus.py archive                     手动触发归档
  bus.py errors                      查看错误日志
  bus.py agent-add <名> --cli <CLI>  注册新 agent
  bus.py agent-remove <名>           移除 agent

配置: data_dir (默认 $MAILBUS_DATA 或 mail/store) 中的 config.json
"""

import os
import sys
import json
import argparse
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.models import (
    Message, MsgStatus, Priority, MsgType, Inbox, AgentConfig, BusConfig,
)
from lib.utils import (
    json_read, json_write, jsonl_append, log_error, resolve_paths,
    build_message, _now_iso, _ensure_dir, file_lock,
)
from lib.scanner import build_queues, run_housekeeping, update_message_status
from lib.pusher import push_messages, resolve_cli_chain, resolve_cli_for_message
from lib.webhook_pusher import push_via_webhook
from lib.ack_handler import scan_ack_files, scan_forward_files, scan_error_reports
from lib.archiver import archive_all
from lib.tracker import TaskTracker
from lib.heartbeat import heartbeat_scan, is_online, load_status
from lib.search import scan_and_index, search
from lib.api import serve as api_serve
from lib.config_schema import validate_config
from lib.constants import (
    DEFAULT_DATA_DIR, DEFAULT_ACK_TIMEOUT, DEFAULT_MAX_RETRIES,
    DEFAULT_ARCHIVE_DAYS, DEFAULT_ARCHIVE_MAX_MESSAGES,
    PROJECT_ROOT_STR,
)


# ── 配置加载 ──────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "project": "ziyan-mailbus",
    "version": "1.0.0",
    "data_dir": DEFAULT_DATA_DIR,
    "ack_timeout": DEFAULT_ACK_TIMEOUT,
    "max_retries": DEFAULT_MAX_RETRIES,
    "archive_days": DEFAULT_ARCHIVE_DAYS,
    "archive_max_messages": DEFAULT_ARCHIVE_MAX_MESSAGES,
    "agents": {},
}


def load_config(config_path: str) -> dict:
    """加载配置，缺失字段用默认值填充，并校验合法性"""
    config = json_read(config_path, {})
    
    # 版本升级迁移
    from .constants import MAILBUS_VERSION
    old_version = config.get("version", "0.0.0")
    if old_version != MAILBUS_VERSION:
        _migrate_config(config, old_version, MAILBUS_VERSION)
        config["version"] = MAILBUS_VERSION
        json_write(config_path, config)
    
    for k, v in DEFAULT_CONFIG.items():
        config.setdefault(k, v)
    # 校验配置合法性
    errors = validate_config(config)
    if errors:
        print(f"⚠️ 配置校验告警 ({config_path}):")
        for err in errors:
            print(f"   - {err}")
    return config


def _migrate_config(config: dict, old_version: str, new_version: str):
    """将配置从旧版本迁移到新版本。每个版本升级写一条规则。"""
    migrations = [
        # v2.0.0 → v2.1.0: 新增 bulletin_authors 等默认字段
        ("2.0.0", "2.1.0", lambda c: c.setdefault("bulletin_authors", {"lingzhao": "灵昭"})),
    ]
    for v_from, v_to, fn in migrations:
        if _version_compare(old_version, v_from) >= 0 and _version_compare(old_version, v_to) < 0:
            print(f"  [migrate] {v_from} → {v_to}")
            fn(config)


def _version_compare(v1: str, v2: str) -> int:
    """语义化版本比较：v1 > v2 → 1, v1 == v2 → 0, v1 < v2 → -1"""
    try:
        p1 = [int(x) for x in v1.split(".")]
        p2 = [int(x) for x in v2.split(".")]
        for a, b in zip(p1, p2):
            if a > b: return 1
            if a < b: return -1
        return len(p1) - len(p2)  # 更长的版本号视为更大
    except (ValueError, AttributeError):
        return 0


def save_config(config_path: str, config: dict):
    """保存配置"""
    json_write(config_path, config)


def get_system_message(agent_name: str) -> dict:
    """生成新 agent 上线时的系统消息"""
    from lib.constants import DEFAULT_DATA_DIR
    inbox_base = f"{DEFAULT_DATA_DIR}/inbox"
    return {
        "id": f"sys-welcome-{agent_name}",
        "from": "mailbus",
        "to": agent_name,
        "priority": "urgent",
        "type": "system",
        "content": f"欢迎 {agent_name} 加入 ziyan-mailbus 消息总线。",
        "reply_format": {
            "ack": {
                "file": f"{inbox_base}/{agent_name}/ack.json",
                "format": {"action": "ack", "msg_id": "<id>", "agent": agent_name, "timestamp": "<ISO时间>"},
            },
            "mark_read": {
                "format": {"action": "mark_read", "msg_ids": ["<id>"], "agent": agent_name, "timestamp": "<ISO时间>"},
            },
            "forward": {
                "target_format": f"{inbox_base}/<目标agent>/inbox.json",
                "format": {
                    "action": "forward", "original_msg_id": "<id>", "from": agent_name,
                    "to": "<目标>", "type": "normal", "priority": "normal",
                    "content": "...", "attachments": [], "timestamp": "<ISO时间>",
                },
            },
        },
        "system_info": {
            "inbox_location": f"{inbox_base}/{agent_name}/inbox.json",
            "inbox_format": f"{inbox_base}/<目标agent>/inbox.json",
            "registered_agents": [],
            "bus_cli_location": f"{PROJECT_ROOT_STR}/bus.py",
            "bus_cron_interval": "每分钟扫描一次",
            "ack_timeout": "30秒",
        },
        "state": MsgStatus.PENDING,
        "created_at": _now_iso(),
    }


# ── CLI 命令实现 ──────────────────────────────────────────────────────

def cmd_init(args) -> int:
    """初始化目录结构 + 创建默认配置（--fresh 从 access/org/config 重建 store）"""
    from .init_store import run_init_store, run_merge_store_config

    data_dir = args.data_dir or DEFAULT_CONFIG["data_dir"]
    if getattr(args, "fresh", False):
        return run_init_store(data_dir, fresh=True)
    if getattr(args, "merge", False):
        return run_merge_store_config(data_dir)

    return run_init_store(data_dir, fresh=False)


def run_scan_once(data_dir: str, config: dict, *, quiet: bool = False) -> int:
    """执行一轮 scan（CLI 与内置 scheduler 共用）。"""
    from .env_bootstrap import load_mailbus_env
    from .utils import configure_stdio_utf8

    configure_stdio_utf8()
    load_mailbus_env()
    from lib.utils import named_lock

    with named_lock("mailbus-scan", blocking=False) as acquired:
        if not acquired:
            log_dir = os.path.join(data_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            skip_log = os.path.join(log_dir, "scan-skipped.jsonl")
            from .utils import jsonl_append, _now_iso
            jsonl_append(skip_log, {
                "ts": _now_iso(),
                "event": "scan_skipped",
                "reason": "mailbus-scan lock held",
            })
            if not quiet:
                print("⏭ scan 跳过（另一实例正在运行，锁 mailbus-scan）")
            return 0
        return _run_scan_once_body(data_dir, config, quiet=quiet)


def _run_scan_once_body(data_dir: str, config: dict, *, quiet: bool = False) -> int:
    """scan 主逻辑（已持有 mailbus-scan 锁）。"""
    _cleanup_stale_locks()

    agents = config.get("agents", {})
    if not agents:
        if not quiet:
            print("✗ 没有注册的 agent，先用 bus.py agent-add 注册")
        return 1

    tracker = TaskTracker(data_dir)

    ack_count = scan_ack_files(data_dir, agents)
    fwd_count = scan_forward_files(data_dir, agents)
    if not quiet:
        if ack_count:
            print(f"✓ 处理了 {ack_count} 条 ack")
        if fwd_count:
            print(f"✓ 处理了 {fwd_count} 条转发")

    try:
        from lib.self_heal import run_self_heal
        healed = run_self_heal(data_dir, agents, phase="pre")
        if healed and not quiet:
            print(f"🔧 自愈: {', '.join(f'{k}={v}' for k, v in healed.items())}")
    except Exception as exc:
        if not quiet:
            print(f"  [scan] self_heal 异常: {exc}")

    try:
        from lib.task_interrupt import detect_interrupted_tasks
        interrupted = detect_interrupted_tasks(data_dir, agents)
        if interrupted and not quiet:
            print(f"⚠️ 断链任务: {len(interrupted)} 个（Dashboard 可继续/recover）")
    except Exception as exc:
        if not quiet:
            print(f"  [scan] interrupt-detect 异常: {exc}")

    urgent_queue, normal_queue = build_queues(data_dir, agents, config)
    total_messages = sum(len(v) for v in urgent_queue.values()) + sum(len(v) for v in normal_queue.values())
    if total_messages == 0:
        run_housekeeping(data_dir, agents)
        if not quiet:
            print("✓ 全员已读，无新消息")
        return 0

    if not quiet:
        print(f"📬 发现 {total_messages} 条待推送消息")
        if urgent_queue:
            print(f"   ⚡ 加急: {sum(len(v) for v in urgent_queue.values())} 条")
        if normal_queue:
            print(f"   📨 普通: {sum(len(v) for v in normal_queue.values())} 条")

    preempted = set()
    if urgent_queue:
        for agent_name in urgent_queue:
            if agent_name in normal_queue:
                preempted.add(agent_name)
                if not quiet:
                    preempted_count = len(normal_queue[agent_name])
                    print(f"   ⚡ {agent_name}: {preempted_count} 条普通消息被加急抢占")
                del normal_queue[agent_name]

    failed_urgent = _push_queue(data_dir, config, urgent_queue, "加急")
    failed_normal = _push_queue(data_dir, config, normal_queue, "普通")
    all_failed = failed_urgent + failed_normal
    if not quiet:
        if all_failed:
            print(f"\n⚠  推送失败: {len(all_failed)} 条（已记录错误日志）")
            for fid in all_failed[:5]:
                print(f"   ✗ {fid}")
            if len(all_failed) > 5:
                print(f"   ... 还有 {len(all_failed) - 5} 条")
        else:
            print(f"\n✓ 全部推送完成")

    run_housekeeping(data_dir, agents)

    reports = scan_error_reports(data_dir, agents)
    if reports:
        if not quiet:
            print(f"\n📕 错误回执: {len(reports)} 条")
        for r in reports:
            tracker.update_status(r['task_id'], 'failed',
                                  {"code": r['error_code'], "reason": r['reason']})
            if not quiet:
                print(f"   → {r['task_id']}: [{r['error_code']}] {r['reason'][:60]}")

    heartbeat_interval = config.get("heartbeat_interval", 300)
    hb_changes = heartbeat_scan(agents, config.get("agent_types", {}), data_dir, config=config,
                                 interval=heartbeat_interval)
    if hb_changes and not quiet:
        for c in hb_changes:
            if c.get("type") == "health":
                print(f"   🔄 AgentMemory: {c['old_status']} → {c['new_status']}")
            else:
                icon = "🟢" if c["new_status"] == "online" else "🔴"
                print(f"   {icon} 心跳 {c['agent']}: {c['old_status']} → {c['new_status']}")

    if not quiet:
        hb_status = load_status(data_dir)
        health = hb_status.get("health", {})
        am = health.get("agentmemory", {})
        if am.get("status") == "unreachable":
            print(f"   ⚠️ AgentMemory 不可用")
        inbox_warnings = health.get("inbox_warnings", [])
        if inbox_warnings:
            for w in inbox_warnings[:3]:
                print(f"   ⚠️ {w['agent']}: inbox {w['count']} 条消息积压")

    # 催办由 run_housekeeping → check_reminders 统一处理（含 inbox 写入），此处不再重复调用

    return 0


def cmd_scan(args) -> int:
    """扫描全员 inbox → 推送未读消息"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    return run_scan_once(data_dir, config, quiet=False)


def cmd_search(args) -> int:
    """消息 / 目录全文检索"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    agents = config.get("agents", {})

    query = getattr(args, "query", "") or ""
    scope = getattr(args, "scope", "messages") or "messages"
    limit = getattr(args, "limit", 20)

    if scope in ("all", "catalog"):
        from lib.catalog_search import index_catalog, search_catalog, search_all
        index_catalog(data_dir, agents)

    if scope == "all":
        bundle = search_all(data_dir, query_str=query, limit=limit, agents=agents)
        msgs = bundle["messages"]
        cats = bundle["catalog"]
        if not msgs and not cats:
            print("无匹配结果")
            return 0
        print(f"\n🔍 查询「{query}」\n")
        if cats:
            print(f"📦 目录/外部工具 ({len(cats)}):\n")
            for r in cats:
                print(f"  [{r['kind']}] {r['title']}")
                if r.get("agent_id") or r.get("tool_id"):
                    print(f"   agent={r.get('agent_id','')} tool={r.get('tool_id','')} provider={r.get('provider','')}")
                print(f"   {r['body'][:120]}")
                print(f"   {r.get('path','')}\n")
        if msgs:
            print(f"📬 消息 ({len(msgs)}):\n")
            for r in msgs:
                print(f"  [{r['status']}] {r['msg_id']}")
                print(f"   {r['from']} → {r['to']} ({r['type']})")
                print(f"   {r['content'][:120]}")
                print()
        return 0

    if scope == "catalog":
        results = search_catalog(data_dir, query_str=query, limit=limit)
        if not results:
            print("无匹配目录项")
            return 0
        print(f"\n📦 找到 {len(results)} 条目录项:\n")
        for r in results:
            print(f"  [{r['kind']}] {r['title']}")
            print(f"   {r['body'][:120]}")
            print(f"   {r.get('path','')}\n")
        return 0

    results = search(
        data_dir,
        query_str=query,
        from_agent=getattr(args, "from_agent", ""),
        to_agent=getattr(args, "to_agent", ""),
        msg_type=getattr(args, "type", ""),
        status=getattr(args, "status", ""),
        limit=limit,
    )

    if not results:
        print("无匹配消息")
        return 0

    print(f"\n🔍 找到 {len(results)} 条匹配消息:\n")
    for r in results:
        print(f"  [{r['status']}] {r['msg_id']}")
        print(f"   {r['from']} → {r['to']} ({r['type']})")
        print(f"   {r['content'][:120]}")
        print(f"   {r.get('created_at', '')}")
        print()

    return 0


def cmd_heartbeat(args) -> int:
    """心跳检测"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    agents = config.get("agents", {})
    agent_types = config.get("agent_types", {})

    if not agents:
        print("✗ 没有注册的 agent")
        return 1

    interval = config.get("heartbeat_interval", 300)
    missed_limit = config.get("heartbeat_missed_limit", 3)

    changes = heartbeat_scan(agents, agent_types, data_dir, config=config, interval=interval, missed_limit=missed_limit,
                              full_health_interval=0)  # 手动触发时总是执行健康检查
    
    # Agent 状态变化
    agent_changes = [c for c in changes if c.get("type") != "health"]
    health_changes = [c for c in changes if c.get("type") == "health"]
    
    if agent_changes:
        print(f"💓 Agent 状态变化: {len(agent_changes)} 条")
        for c in agent_changes:
            icon = "🟢" if c["new_status"] == "online" else "🔴" if c["new_status"] == "offline" else "⚠️"
            print(f"   {icon} {c['agent']}: {c['old_status']} → {c['new_status']}")
    else:
        print("💓 Agent 心跳正常")
    
    # 健康状态
    hb_status = load_status(data_dir)
    health = hb_status.get("health", {})
    
    # AgentMemory
    am = health.get("agentmemory", {})
    am_status = am.get("status", "unknown")
    am_icon = "🟢" if am_status == "healthy" else "🔴" if am_status == "unreachable" else "⚠️"
    print(f"   {am_icon} AgentMemory: {am_status}" + (f" ({am.get('detail','')})" if am.get('detail') else ""))
    
    # 磁盘
    disk = health.get("disk", {})
    if disk.get("status") == "warn":
        print(f"   ⚠️  磁盘: {disk['size_mb']}MB（超过告警阈值 {disk['warn_mb']}MB）")
    elif disk.get("size_mb"):
        print(f"   💾 磁盘: {disk['size_mb']}MB")
    
    # inbox 积压
    inbox_warnings = health.get("inbox_warnings", [])
    if inbox_warnings:
        for w in inbox_warnings:
            level_icon = "🔴" if w["level"] == "critical" else "⚠️"
            print(f"   {level_icon} {w['agent']}: inbox {w['count']} 条消息积压")

    if health_changes:
        for c in health_changes:
            print(f"   🔄 AgentMemory: {c['old_status']} → {c['new_status']}")
    
    return 0


def cmd_serve(args) -> int:
    """启动 HTTP API 服务"""
    from .env_bootstrap import load_mailbus_env

    load_mailbus_env()
    config_path = _find_config(args)
    config = load_config(config_path)
    if getattr(args, 'data_dir', None):
        config = dict(config)
        config["data_dir"] = args.data_dir
    data_dir = config["data_dir"]

    try:
        from lib.internal_llm.startup import maybe_rebuild_rag_on_start

        rag_result = maybe_rebuild_rag_on_start(data_dir)
        if rag_result and rag_result.get("rebuilt"):
            print(f"  📚 RAG rebuild_on_start: {rag_result['chunks']} chunks indexed")
    except Exception as exc:
        print(f"  ⚠️ RAG rebuild_on_start skipped: {exc}")
    from lib.constants import DEFAULT_API_PORT

    agents = config.get("agents", {})
    agent_types = config.get("agent_types", {})
    port = getattr(args, "port", None) or DEFAULT_API_PORT

    if not agents:
        print("✗ 没有注册的 agent")
        return 1

    token = getattr(args, 'token', '') or config.get("api_token", "") or os.environ.get("MAILBUS_API_TOKEN", "")
    if token:
        print("  🔑 API 认证已启用（Bearer / X-API-Key）")
    elif config.get("require_api_auth"):
        print("  ⚠️ require_api_auth=true 但未配置 api_token — 写操作 API 将返回 503")
    api_serve(data_dir, agents, agent_types, host=args.host, port=port, token=token, config=config)
    return 0


def cmd_launch(args) -> int:
    """启动/停止 agent 常驻进程

    根据 config.json 中 agents 的 launch 配置，启动或停止各类常驻进程。

    用法:
      bus.py launch                   启动所有需要常驻的 agent
      bus.py launch --agent xiaoqi    启动指定 agent
      bus.py launch --stop            停止所有 agent 进程
      bus.py launch --status          查看运行状态
    """
    config_path = _find_config(args)
    config = load_config(config_path)
    agents = config.get("agents", {})
    agent_types = config.get("agent_types", {})
    templates = agent_types.get("launch_templates", {})
    data_dir = config.get("data_dir", "")

    stop_mode = getattr(args, "stop", False)
    status_mode = getattr(args, "status", False)
    agent_filter = getattr(args, "agent", "")

    # ── --status: 查看状态 ──────────────────────────────────────────
    if status_mode:
        print("")
        print("📊 Agent 进程状态 (bus.py launch --status)")
        print("──────────────────────────────────────────")
        for name, cfg in agents.items():
            launch = cfg.get("launch", {})
            template_name = launch.get("template", "")
            has_browser = launch.get("has_browser", False)
            browser_cfg = launch.get("browser", {})

            # 检测是否在运行
            port = browser_cfg.get("gateway_port") or browser_cfg.get("dashboard_port") or \
                   browser_cfg.get("port", "")
            if port:
                port_check = subprocess.run(
                    ["ss", "-tlnp"], capture_output=True, text=True, timeout=5
                )
                if f":{port} " in port_check.stdout:
                    print(f"  ✅ {cfg.get('name', name)} ({name}) — :{port} 监听中")
                else:
                    print(f"  ❌ {cfg.get('name', name)} ({name}) — :{port} 未启动")
            elif template_name == "url_only":
                print(f"  ⚪ {cfg.get('name', name)} ({name}) — CLI 模式，无常驻进程")
            else:
                # 尝试 pgrep
                proc_check = subprocess.run(
                    ["pgrep", "-f", name], capture_output=True, text=True, timeout=5
                )
                if proc_check.returncode == 0:
                    print(f"  ✅ {cfg.get('name', name)} ({name}) — PID: {proc_check.stdout.strip()}")
                else:
                    print(f"  ❌ {cfg.get('name', name)} ({name}) — 未运行")
        # ── 显示 inbox 积压情况 ──────────────────────────────
        print("📦 Inbox 积压:")
        import os as _os
        for name, cfg in agents.items():
            inbox_path = cfg.get("inbox", f"{data_dir}/inbox/{name}/inbox.json")
            if _os.path.exists(inbox_path):
                fsize = _os.path.getsize(inbox_path)
                try:
                    with open(inbox_path) as _f:
                        _d = json.load(_f)
                    mcount = len(_d.get("messages", []))
                    unread = _d.get("has_unread", False)
                    flag = " 📩" if unread else ""
                    print(f"  {cfg.get('name', name)}: {mcount} 条 / {fsize//1024}K{flag}")
                except (json.JSONDecodeError, OSError):
                    print(f"  {cfg.get('name', name)}: {fsize//1024}K (读取失败)")
        print("")
        return 0

    # ── --stop: 停止所有 ────────────────────────────────────────────
    if stop_mode:
        print("")
        print("🛑 停止 agent 常驻进程...")
        print("──────────────────────────")
        for name, cfg in agents.items():
            if agent_filter and name != agent_filter:
                continue
            launch = cfg.get("launch", {})
            browser_cfg = launch.get("browser", {})
            start_cmd = browser_cfg.get("start_command", "")
            if not start_cmd:
                continue

            # 通过端口获取 PID 来杀（比 pgrep/pkill 可靠）
            port = (browser_cfg.get("gateway_port") or
                    browser_cfg.get("dashboard_port") or
                    browser_cfg.get("port", ""))
            if not port:
                print(f"  ⚠️ {cfg.get('name', name)} ({name}): 无端口配置，跳过")
                continue

            # 用 ss 获取监听该端口的 PID
            try:
                ss_out = subprocess.run(
                    ["ss", "-tlnp"],
                    capture_output=True, text=True, timeout=5
                ).stdout
                for line in ss_out.splitlines():
                    if f":{port} " in line and "pid=" in line:
                        # 提取所有 PID
                        import re
                        pids = re.findall(r'pid=(\d+)', line)
                        for pid in pids:
                            subprocess.run(["kill", pid], capture_output=True, timeout=5)
                            print(f"  ✅ 已停止: {cfg.get('name', name)} ({name}:{port}) — PID {pid}")
                        break
                else:
                    print(f"  ⚪ {cfg.get('name', name)} ({name}): :{port} 未监听，无需停止")
            except Exception as e:
                print(f"  ⚠️ {cfg.get('name', name)} ({name}): 停止失败 — {e}")
        print("")
        return 0

    # ── 默认：启动 agent ────────────────────────────────────────────
    print("")
    print("╔══════════════════════════════════════════╗")
    print("║   🚀 mailbus agent 启动                  ║")
    print("╚══════════════════════════════════════════╝")
    print("")

    launched = 0
    skipped = 0
    for name, cfg in agents.items():
        if agent_filter and name != agent_filter:
            continue

        launch = cfg.get("launch", {})
        template_name = launch.get("template", "")
        if template_name == "url_only":
            print(f"  ⚪ {cfg.get('name', name)} ({name}): CLI 模式，跳过")
            skipped += 1
            continue

        browser_cfg = launch.get("browser", {})
        start_cmd = browser_cfg.get("start_command", "")
        if not start_cmd:
            print(f"  ⚪ {cfg.get('name', name)} ({name}): 无启动命令，跳过")
            skipped += 1
            continue

        # 检查端口是否已被占用
        port = browser_cfg.get("gateway_port") or browser_cfg.get("dashboard_port") or \
               browser_cfg.get("port", "")
        if port:
            port_check = subprocess.run(
                ["ss", "-tlnp"], capture_output=True, text=True, timeout=5
            )
            if f":{port} " in port_check.stdout:
                print(f"  ⚠️  {cfg.get('name', name)} ({name}): :{port} 已在监听，跳过")
                skipped += 1
                continue

        # 执行启动命令
        log_file = f"/tmp/mailbus-{name}-launch.log"
        full_cmd = f"{start_cmd} > {log_file} 2>&1 &"
        print(f"  🚀 {cfg.get('name', name)} ({name}): {start_cmd[:80]}...")

        try:
            subprocess.run(
                ["nohup", "sh", "-c", start_cmd],
                stdout=open(log_file, "w"),
                stderr=subprocess.STDOUT,
                start_new_session=True,
                timeout=30,
            )
            launched += 1
            print(f"     ✅ 已启动 (日志: {log_file})")
        except Exception as e:
            print(f"     ❌ 启动失败: {e}")

    print("")
    print(f"📊 结果: {launched} 个启动, {skipped} 个跳过")
    print("💡 查看状态: bus.py launch --status")
    print("")
    return 0


def _push_queue(data_dir: str, config: dict, queue: dict, label: str) -> list:
    """推送一个队列（加急/普通）"""
    agent_types = config.get("agent_types", {})
    all_failed = []
    for agent_name, messages in queue.items():
        agent_cfg = config["agents"].get(agent_name)
        if not agent_cfg:
            print(f"   ⚠ {agent_name}: 配置不存在，跳过")
            continue
        
        webhook_url = agent_cfg.get("webhook_url", "")
        if webhook_url:
            print(f"   🌐 {agent_name} ({label}): {len(messages)} 条 [Webhook]")
            # auto_ack 判定：pipeline 步骤禁止 auto_ack
            from .pipeline_task import should_auto_ack_message
            msg0 = messages[0] if messages else {}
            auto_ack = should_auto_ack_message(
                msg0, data_dir, agent_cfg.get("type", ""),
            ) if agent_cfg.get("type") in ("hermes", "hermes_profile", "openclaw") else False
            failed = push_via_webhook(
                data_dir=data_dir,
                agent_name=agent_name,
                messages=messages,
                webhook_url=webhook_url,
                webhook_secret=agent_cfg.get("webhook_secret", ""),
                max_retries=config.get("max_retries", 3),
                auto_ack=auto_ack,
            )
        else:
            from .model_router import is_no_llm_notice
            from .scanner import _get_primary_pipeline_task_id

            primary_tid = _get_primary_pipeline_task_id(data_dir)
            # 零 token：系统 notice 直接 done，不 spawn Hermes
            skip_msgs = [m for m in messages if is_no_llm_notice(m)]
            if skip_msgs:
                paths = resolve_paths(data_dir)
                inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
                inbox_data = json_read(inbox_file, {})
                if inbox_data:
                    inbox = Inbox.from_dict(inbox_data)
                    ts = _now_iso()
                    for m in skip_msgs:
                        mid = m.get("id") if isinstance(m, dict) else m.id
                        inbox.set_msg_status(
                            mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE,
                            done_at=ts, done_note="auto: no-llm notice",
                        )
                    json_write(inbox_file, inbox.to_dict())
                messages = [m for m in messages if not is_no_llm_notice(m)]
                if not messages:
                    print(f"     ✓ {len(skip_msgs)} 条 notice 已自动消化（零 token）")
                    continue

            msg0 = messages[0]
            cli_cmd = resolve_cli_for_message(
                agent_cfg, agent_types, msg0, agent_name,
                primary_task_id=primary_tid, data_dir=data_dir,
            )
            if not cli_cmd:
                print(f"   → {agent_name} ({label}): 跳过（无需 LLM）")
                continue
            print(f"   → {agent_name} ({label}): {len(messages)} 条")
            auto_ack_types = ("hermes", "hermes_profile", "openclaw")
            from .pipeline_task import should_auto_ack_message
            auto_ack = should_auto_ack_message(
                msg0, data_dir, agent_cfg.get("type", ""),
            )
            failed = push_messages(
                data_dir=data_dir,
                agent_name=agent_name,
                messages=messages,
                cli_cmd=cli_cmd,
                ack_timeout=config.get("ack_timeout", 30),
                max_retries=config.get("max_retries", 3),
                auto_ack=auto_ack,
            )
        all_failed.extend(failed)
        
        if failed:
            print(f"     ✗ {len(failed)} 条推送失败")
        else:
            print(f"     ✓ 全部送达")
    
    return all_failed


def cmd_send(args) -> int:
    """手动发消息给指定 agent（支持 --domain 批量路由）"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    agents = config.get("agents", {})
    
    # 解析参数
    to = args.agent
    content = args.msg
    from_ = getattr(args, 'from_', None) or "manual"
    priority = getattr(args, 'priority', Priority.NORMAL)
    msg_type = getattr(args, 'type', MsgType.NOTICE)
    domain = getattr(args, 'domain', "") or ""
    project = getattr(args, 'project', "") or ""
    
    # ── 任务追踪（仅 task / task_reply 类型） ──
    if msg_type in (MsgType.TASK, MsgType.TASK_REPLY):
        tracker = TaskTracker(data_dir)
    
    # ── Domain 路由模式 ──
    if not to and domain:
        from lib.utils import load_registry, resolve_domain_to_agents
        registry = load_registry(data_dir)
        targets = resolve_domain_to_agents(domain, registry)
        if not targets:
            print(f"✗ domain '{domain}' 没有匹配的 agent")
            print(f"  可用 domain 请查看 store/registry.json")
            return 1
        # 过滤出已注册的 agent
        targets = [t for t in targets if t in agents]
        if not targets:
            print(f"✗ domain '{domain}' 匹配的 agent 均未注册到总线")
            return 1
        print(f"  → Domain '{domain}' 匹配 {len(targets)} 个 agent: {', '.join(targets)}")
        success_count = 0
        for target in targets:
            msg = build_message(from_, target, content, msg_type, priority,
                                forward_to=getattr(args, 'forward_to', None),
                                project=project or None)
            _write_to_inbox(data_dir, target, msg)
            if msg_type in (MsgType.TASK, MsgType.TASK_REPLY):
                try:
                    tracker.create(task_id=msg.id, summary=content[:80], assignee=target, requires_audit=False)
                except Exception as e:
                    print(f"  ⚠️ 任务追踪创建失败: {e}")
            success_count += 1
            print(f"  ✓ 已写入 {target}")
        print(f"✓ 消息已发送给 {success_count} 个 agent (domain={domain})")
        print(f"  下个 cron 周期将自动推送")
        return 0
    
    # ── 单 agent 模式 ──
    if not to:
        print("✗ 请指定 agent 名称或使用 --domain")
        return 1
    if to not in agents:
        print(f"✗ agent '{to}' 未注册")
        print(f"  已注册: {', '.join(agents.keys())}")
        return 1
    
    agent_types = config.get("agent_types", {})
    cli_cmds = [c[0] for c in resolve_cli_chain(agents[to], agent_types)]
    print(f"  CLI: {' | '.join(cli_cmds[:3]) or '(纯文件通信)'}")
    
    # 构建消息
    msg = build_message(from_, to, content, msg_type, priority,
                        forward_to=getattr(args, 'forward_to', None),
                        project=project or None)
    msg_dict = msg.to_dict()
    from .pipeline_task import extract_task_id
    ptid = extract_task_id(content)
    if ptid and not ptid.startswith("msg-"):
        msg_dict["task_id"] = ptid
    _write_to_inbox(data_dir, to, msg_dict)
    # 即时推送（与 /api/send-msg 一致，不等待 cron scan）
    try:
        from .model_router import is_no_llm_notice
        from .scanner import finalize_auto_ack

        if is_no_llm_notice(msg_dict):
            finalize_auto_ack(data_dir, to, msg_dict["id"], msg_dict)
            print("  ✓ notice 已自动消化（零 token）")
        else:
            cli_chain = resolve_cli_chain(agents[to], agent_types)
            if cli_chain:
                cli_cmds = [c[0] for c in cli_chain]
                from .pipeline_task import should_auto_ack_message
                auto_ack = should_auto_ack_message(
                    msg_dict, data_dir, agents[to].get("type", ""),
                )
                push_messages(data_dir, to, [msg_dict], cli_cmd=cli_cmds, auto_ack=auto_ack)
                print("  ✓ 即时推送已触发")
    except Exception as exc:
        print(f"  ⚠️ 即时推送失败: {exc}")
    if msg_type in (MsgType.TASK, MsgType.TASK_REPLY):
        from .pipeline_task import extract_task_id, should_create_tracker_for_send

        if should_create_tracker_for_send(content, data_dir):
            try:
                tracker.create(task_id=msg_dict["id"], summary=content[:80], assignee=to, requires_audit=False)
            except Exception as e:
                print(f"  ⚠️ 任务追踪创建失败: {e}")
        else:
            tid = extract_task_id(content)
            print(f"  ℹ️ 跳过重复 tracker（已存在 pipeline task {tid}）")
    print(f"✓ 消息已写入 {to} 的 inbox")
    print(f"  ID: {msg_dict['id']}")
    print(f"  内容: {content[:60]}{'...' if len(content) > 60 else ''}")
    if project:
        print(f"  项目: {project}")
    return 0


def _write_to_inbox(data_dir: str, agent_name: str, msg):
    """将消息写入指定 agent 的 inbox（Message 或 dict）。"""
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
    inbox_data = json_read(inbox_file, {"agent": agent_name, "has_unread": False, "messages": [], "since": _now_iso()})
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    entry = msg.to_dict() if hasattr(msg, "to_dict") else msg
    inbox.messages.append(entry)
    json_write(inbox_file, inbox.to_dict())


def cmd_broadcast(args) -> int:
    """发公告板（支持 --domain 过滤）"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    agents = config.get("agents", {})
    
    if not agents:
        print("✗ 没有注册的 agent")
        return 1
    
    content = args.msg
    priority = getattr(args, 'priority', Priority.NORMAL)
    domain = getattr(args, 'domain', "") or ""
    
    # ── Domain 过滤 ──
    targets = list(agents.keys())
    if domain:
        from lib.utils import load_registry, resolve_domain_to_agents
        registry = load_registry(data_dir)
        domain_agents = resolve_domain_to_agents(domain, registry)
        targets = [t for t in targets if t in domain_agents]
        if not targets:
            print(f"✗ domain '{domain}' 没有匹配的已注册 agent")
            return 1
    
    # 写入公告板
    paths = resolve_paths(data_dir)
    board_data = json_read(paths["board"], {"board": [], "created_at": _now_iso()})
    
    board_msg = {
        "id": f"board-{_now_iso()[:10]}-{len(board_data['board']) + 1}",
        "content": content,
        "priority": priority,
        "created_at": _now_iso(),
        "domain": domain or None,
    }
    board_data["board"].append(board_msg)
    json_write(paths["board"], board_data)
    
    # 写入每个目标 agent 的 inbox
    from_ = "broadcast"
    for name in targets:
        msg = build_message(from_, name, content, MsgType.NOTICE, priority)
        _write_to_inbox(data_dir, name, msg)
    
    print(f"✓ 公告已发送给 {len(targets)} 个 agent" + (f" (domain={domain})" if domain else ""))
    return 0


def cmd_ack(args) -> int:
    """agent 确认收到"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    
    msg_id = args.msg_id
    agent_name = getattr(args, 'agent', None)
    
    if not agent_name:
        # 尝试从消息本身推断 agent
        print("✗ 请指定 agent 名称")
        return 1
    
    ack_data = {
        "action": "ack",
        "msg_id": msg_id,
        "agent": agent_name,
        "timestamp": _now_iso(),
    }
    
    # 写入 ack.json
    paths = resolve_paths(data_dir)
    ack_dir = f"{paths['inbox']}/{agent_name}"
    _ensure_dir(ack_dir)
    json_write(f"{ack_dir}/ack.json", ack_data)
    
    print(f"✓ ack 已提交: {msg_id}")
    return 0


def cmd_mark_read(args) -> int:
    """agent 标记已读"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    
    msg_ids = args.msg_ids.split(",")
    agent_name = getattr(args, 'agent', None)
    
    if not agent_name:
        print("✗ 请指定 agent 名称")
        return 1
    
    mark_data = {
        "action": "mark_read",
        "msg_ids": msg_ids,
        "agent": agent_name,
        "timestamp": _now_iso(),
    }
    
    paths = resolve_paths(data_dir)
    mark_dir = f"{paths['inbox']}/{agent_name}"
    _ensure_dir(mark_dir)
    json_write(f"{mark_dir}/mark.json", mark_data)
    
    print(f"✓ 已标记 {len(msg_ids)} 条消息为已读")
    return 0


def cmd_status(args) -> int:
    """查看消息状态"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    agents = config.get("agents", {})
    
    paths = resolve_paths(data_dir)
    
    if args.failed:
        # 查看失败消息
        error_dir = paths["errors"]
        if not os.path.isdir(error_dir):
            print("无错误日志")
            return 0
        
        for fname in sorted(os.listdir(error_dir)):
            if fname.endswith(".jsonl"):
                count = sum(1 for _ in open(f"{error_dir}/{fname}"))
                print(f"  {fname}: {count} 条错误")
        return 0
    
    if args.agent:
        # 查看指定 agent
        name = args.agent
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            print(f"  {name}: 无数据")
            return 0
        
        inbox = Inbox.from_dict(inbox_data)
        print(f"\n📬 {name}:")
        print(f"  消息总数: {len(inbox.messages)}")
        for m in inbox.messages:
            s = inbox.msg_field(m, 'state', '') or inbox.msg_field(m, 'status', '')
            print(f"  [{s}] {inbox.msg_field(m, 'id')} — {inbox.msg_field(m, 'content', '')[:40]}")
        return 0
    
    # 查看所有
    print(f"\n📋 消息总线状态 ({_now_iso()[:19]}):")
    print(f"  注册 agent: {', '.join(agents.keys()) if agents else '无'}")
    print()
    
    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            print(f"  {name}: 空")
            continue
        
        inbox = Inbox.from_dict(inbox_data)
        statuses = {}
        for m in inbox.messages:
            s = inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "unknown")
            statuses[s] = statuses.get(s, 0) + 1
        
        parts = [f"{s}: {c}" for s, c in sorted(statuses.items())]
        print(f"  {name}: {', '.join(parts) if parts else '空'}")

    bridge_file = os.path.join(data_dir, "system", "memory-bridge-last.json")
    bridge_stats = json_read(bridge_file, {})
    if bridge_stats:
        print()
        print("  记忆桥接 (末次):")
        print(f"    sqlite: {bridge_stats.get('sqlite_ok', 0)} ok, "
              f"{bridge_stats.get('sqlite_fail', 0)} fail")
        print(f"    agentmemory: {bridge_stats.get('agentmemory_ok', 0)} ok, "
              f"{bridge_stats.get('agentmemory_skip', 0)} skip")
        print(f"    更新: {bridge_stats.get('updated_at', '?')}")

    wd_file = os.path.join(data_dir, "system", "agentmemory-watchdog.json")
    wd_stats = json_read(wd_file, {})
    if wd_stats:
        print("  AgentMemory 看门狗:")
        print(f"    状态: {wd_stats.get('last_status', '?')} "
              f"(streak={wd_stats.get('fail_streak', 0)})")
        if wd_stats.get("last_restart_attempt"):
            print(f"    末次重启: {wd_stats.get('last_restart_attempt')} "
                  f"ok={wd_stats.get('last_restart_ok')}")

    return 0


def cmd_retry(args) -> int:
    """重试失败消息"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    agents = config.get("agents", {})
    paths = resolve_paths(data_dir)
    
    if args.msg_id:
        # 重试单条 — 需要找到它在哪个 agent 的 inbox
        found = False
        for name in agents:
            inbox_file = f"{paths['inbox']}/{name}/inbox.json"
            inbox_data = json_read(inbox_file, {})
            if not inbox_data:
                continue
            inbox = Inbox.from_dict(inbox_data)
            for m in inbox.messages:
                if inbox.msg_field(m, "id") == args.msg_id:
                    inbox.set_msg_status(args.msg_id, MsgStatus.PENDING, pushed_count=0)
                    json_write(inbox_file, inbox.to_dict())
                    print(f"✓ {args.msg_id} 已重置为 pending，下个 cron 将重试")
                    found = True
                    break
            if found:
                break
        if not found:
            print(f"✗ 未找到消息: {args.msg_id}")
        return 0
    
    # 重试所有 failed
    count = 0
    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            continue
        inbox = Inbox.from_dict(inbox_data)
        changed = False
        for m in inbox.messages:
            if inbox.msg_field(m, "status") == MsgStatus.FAILED:
                inbox.set_msg_status(inbox.msg_field(m, "id"), MsgStatus.RESENDING, pushed_count=0)
                changed = True
                count += 1
        if changed:
            json_write(inbox_file, inbox.to_dict())
    
    print(f"✓ 重置了 {count} 条失败消息为待重试")
    if count > 0:
        print("  运行 bus.py scan 即可重新推送")
    return 0


def cmd_archive(args) -> int:
    """手动触发归档"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    agents = config.get("agents", {})
    
    if not agents:
        print("✗ 没有注册的 agent")
        return 1
    
    results = archive_all(data_dir, agents, config.get("archive_days", 3), config.get("archive_max_messages", 300))
    
    if not results:
        print("✓ 无需归档")
        return 0
    
    for name, count in results.items():
        print(f"  {name}: 归档 {count} 条")
    
    total = sum(results.values())
    print(f"\n✓ 共归档 {total} 条消息")
    return 0


def cmd_backup(args) -> int:
    """备份 store/ 目录到 backup/"""
    import shutil, datetime
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    
    backup_dir = os.path.join(os.path.dirname(data_dir), "backup")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"store-backup-{ts}.tar.gz"
    archive_path = os.path.join(backup_dir, archive_name)
    
    os.makedirs(backup_dir, exist_ok=True)
    
    # 用 tar 压缩，排除大的临时文件
    import subprocess
    result = subprocess.run(
        ["tar", "-czf", archive_path, "-C", os.path.dirname(data_dir), "store",
         "--exclude=store/search.db", "--exclude=store/heartbeat.json"],
        capture_output=True, text=True, timeout=60
    )
    
    if result.returncode == 0:
        size_mb = os.path.getsize(archive_path) / 1024 / 1024
        print(f"✅ 备份完成: {archive_name} ({size_mb:.1f} MB)")
        # 保留最近 7 个备份，删除更早的
        backups = sorted([f for f in os.listdir(backup_dir) if f.startswith("store-backup-")])
        while len(backups) > 7:
            old = backups.pop(0)
            os.remove(os.path.join(backup_dir, old))
            print(f"  删除旧备份: {old}")
        return 0
    else:
        print(f"❌ 备份失败: {result.stderr}")
        return 1


def cmd_errors(args) -> int:
    """查看错误日志"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    paths = resolve_paths(data_dir)
    
    error_dir = paths["errors"]
    if not os.path.isdir(error_dir):
        print("无错误日志")
        return 0
    
    files = sorted(os.listdir(error_dir))
    if not files:
        print("无错误日志")
        return 0
    
    for fname in files[-5:]:  # 只看最近 5 个文件
        path = f"{error_dir}/{fname}"
        with open(path) as f:
            lines = f.readlines()
        print(f"\n📄 {fname} ({len(lines)} 条):")
        for line in lines[-10:]:  # 每个文件看最近 10 条
            entry = json.loads(line)
            print(f"  [{entry['level']}] {entry.get('msg_id', '?')} → {entry.get('to', '?')}: {entry.get('error', '?')}")
    
    return 0


def cmd_agent_add(args) -> int:
    """注册新 agent"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    
    # register
    name = args.agent
    atype = args.type or "none"
    role = getattr(args, 'role', "")
    agent_id = getattr(args, 'agent_id', None) or name
    profile = getattr(args, 'profile', None)
    cli = getattr(args, "cli", "") or ""

    if name in config["agents"]:
        print(f"✗ agent '{name}' 已存在")
        print("  如需修改，请直接编辑配置文件")
        return 1
    
    if atype != "none" and atype not in config.get("agent_types", {}):
        print(f"✗ 未知类型 '{atype}'")
        print(f"  可用类型: {', '.join(config.get('agent_types', {}).keys())}")
        return 1
    
    # 注册到配置
    agent_entry = {
        "name": name,
        "role": role,
        "type": atype,
        "inbox": f"{data_dir}/inbox/{name}/inbox.json",
    }
    if atype == "hermes_profile":
        agent_entry["profile"] = profile or name
    if atype == "openclaw":
        agent_entry["agent"] = agent_id
    config["agents"][name] = agent_entry
    save_config(config_path, config)
    
    # 创建 inbox 目录
    paths = resolve_paths(data_dir)
    inbox_dir = f"{paths['inbox']}/{name}"
    _ensure_dir(inbox_dir)
    
    # 写一条系统欢迎消息
    sys_msg = get_system_message(name)
    sys_msg["system_info"]["registered_agents"] = list(config["agents"].keys())
    json_write(f"{inbox_dir}/inbox.json", {
        "agent": name,
        "has_unread": True,
        "messages": [sys_msg],
        "since": _now_iso(),
    })
    
    print(f"✓ agent '{name}' 已注册")
    print(f"  收件箱: {inbox_dir}/inbox.json")
    print(f"  CLI: {cli or '未设置（仅文件级通信）'}")
    print(f"  首条系统消息已写入 inbox")
    return 0


def cmd_agent_remove(args) -> int:
    """移除 agent"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    
    name = args.agent
    if name not in config["agents"]:
        print(f"✗ agent '{name}' 不存在")
        return 1
    
    # 从配置移除
    del config["agents"][name]
    save_config(config_path, config)
    
    # 保留 inbox 数据（不删除，避免意外丢失）
    print(f"✓ agent '{name}' 已从总线移除")
    print(f"  inbox 数据保留在: {config['data_dir']}/inbox/{name}/")
    print(f"  如需删除: rm -rf {config['data_dir']}/inbox/{name}")
    return 0


def cmd_review(args) -> int:
    """代码审查：pylint + mypy 静态检查 + review.py AI 审查 + semgrep 安全扫描"""
    import subprocess

    config_path = _find_config(args)
    config = load_config(config_path)

    workdir = args.workdir or os.getcwd()
    if not os.path.isdir(workdir):
        print(f"✗ 目录不存在: {workdir}")
        return 1

    output_lines = []
    def emit(line=""):
        print(line)
        output_lines.append(line)

    # ── 0. 收集改动的 Python 文件 ──
    changed_py_files = []
    if args.commit:
        try:
            r = subprocess.run(
                ["git", "diff", "--name-only", f"{args.commit}^..{args.commit}"],
                cwd=workdir, capture_output=True, text=True, timeout=30
            )
            if r.returncode == 0:
                changed_py_files = [
                    os.path.join(workdir, f) for f in r.stdout.strip().splitlines()
                    if f.endswith(".py")
                ]
        except Exception:
            pass
    emit(f"🔍 代码审查开始: {workdir}")
    if changed_py_files:
        emit(f"   改动 Python 文件 ({len(changed_py_files)} 个):")
        for f in changed_py_files:
            emit(f"     - {os.path.relpath(f, workdir)}")

    # ── 1. pylint 静态检查 ──
    pylint_exit = 0
    mypy_exit = 0
    if changed_py_files:
        pylint_output = ""
        if shutil.which("pylint"):
            emit("\n── pylint ──")
            try:
                r = subprocess.run(
                    ["pylint", "--output-format=text", "--score=n"] + changed_py_files,
                    cwd=workdir, capture_output=True, text=True, timeout=60
                )
                pylint_output = r.stdout
                if r.stdout.strip():
                    emit(r.stdout)
                if r.returncode != 0:
                    pylint_exit = r.returncode
                    # 非致命：pylint 1-4 表示有 issue
            except subprocess.TimeoutExpired:
                emit("⚠ pylint 超时（60秒）")
            except Exception as e:
                emit(f"⚠ pylint 执行异常: {e}")
        else:
            emit("⚠ pylint 不可用，跳过")

    # ── 2. mypy 类型检查 ──
    if changed_py_files:
        mypy_output = ""
        if shutil.which("mypy"):
            emit("\n── mypy ──")
            try:
                r = subprocess.run(
                    ["mypy", "--show-error-codes"] + changed_py_files,
                    cwd=workdir, capture_output=True, text=True, timeout=60
                )
                mypy_output = r.stdout
                if r.stdout.strip():
                    emit(r.stdout)
                if r.returncode != 0:
                    mypy_exit = r.returncode
            except subprocess.TimeoutExpired:
                emit("⚠ mypy 超时（60秒）")
            except Exception as e:
                emit(f"⚠ mypy 执行异常: {e}")
        else:
            emit("⚠ mypy 不可用，跳过")

    # ── 3. semgrep 安全扫描 ──
    semgrep_exit = 0
    if getattr(args, "semgrep", False):
        from .constants import MAILBUS_ROOT

        semgrep_rules_dir = str(MAILBUS_ROOT / "config" / "review" / "semgrep")
        legacy_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "semgrep-rules"))
        if not os.path.isdir(semgrep_rules_dir) and os.path.isdir(legacy_dir):
            semgrep_rules_dir = legacy_dir
        semgrep_exit = 0
        if shutil.which("semgrep") and os.path.isdir(semgrep_rules_dir):
            target_dir = args.target or "."
            target_path = os.path.join(workdir, target_dir) if not os.path.isabs(target_dir) else target_dir
            if not os.path.isdir(target_path):
                target_path = workdir
            emit("\n── semgrep ──")
            try:
                r = subprocess.run(
                    ["semgrep", "scan", "--config", semgrep_rules_dir,
                     "--json", target_path],
                    cwd=workdir, capture_output=True, text=True, timeout=120
                )
                if r.returncode in (0, 1):
                    import json as _json
                    try:
                        data = _json.loads(r.stdout)
                        results = data.get("results", [])
                        if results:
                            emit(f"  发现 {len(results)} 个安全问题:")
                            for res in results:
                                path = res.get("path", "")
                                line = res.get("start", {}).get("line", "")
                                check_id = res.get("check_id", "").split(".", 1)[-1]
                                msg = res.get("extra", {}).get("message", "")
                                emit(f"    • {path}:{line} [{check_id}] {msg}")
                        else:
                            emit("  未发现安全问题 ✓")
                        semgrep_exit = len(results)
                    except (_json.JSONDecodeError, Exception) as e:
                        emit(f"⚠ semgrep 输出解析失败: {e}")
                        if r.stdout:
                            emit(r.stdout[:500])
                else:
                    emit(f"⚠ semgrep 异常退出 (exit={r.returncode})")
                    if r.stderr:
                        emit(f"  stderr: {r.stderr[:300]}")
            except subprocess.TimeoutExpired:
                emit("⚠ semgrep 超时（120秒）")
            except Exception as e:
                emit(f"⚠ semgrep 执行异常: {e}")
        else:
            if not shutil.which("semgrep"):
                emit("⚠ semgrep 不可用，跳过")
            if not os.path.isdir(semgrep_rules_dir):
                emit(f"⚠ semgrep 规则目录不存在: {semgrep_rules_dir}")

    # ── 4. review.py AI 审查 diff ──
    review_script = config.get("review_script", "")
    if not review_script:
        review_script = os.environ.get("MAILBUS_REVIEW_SCRIPT", "")
    if not review_script:
        mail_home = os.environ.get("MAIL_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        review_script = os.path.join(mail_home, "..", "pr-agent", "review.py")
    review_script = os.path.normpath(review_script)
    if os.path.isfile(review_script):
        emit("\n── AI 代码审查 ──")
        cmd = [sys.executable, review_script]
        if args.commit:
            cmd += ["--commit", args.commit]
        if args.output:
            cmd += ["--output", args.output]
        if args.target:
            cmd += ["--target-dir", args.target]

        # review.py 内部会自己读 ~/.hermes/.env，不需要通过 env 传 key
        # 避免 DEEPSEEK_API_KEY 通过子进程 /proc/PID/environ 泄露
        try:
            r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=180)
            if r.stdout:
                emit(r.stdout)
            if r.stderr:
                emit(f"⚠ stderr: {r.stderr[:300]}")
        except subprocess.TimeoutExpired:
            emit("✗ AI 审查超时（180秒）")
        except Exception as e:
            emit(f"✗ AI 审查失败: {e}")
    else:
        emit("⚠ review.py 未找到，跳过 AI 审查")

    # ── 5. 写入报告 ──
    if args.output:
        try:
            _ensure_dir(os.path.dirname(args.output))
            with open(args.output, "w", encoding="utf-8") as f:
                f.write("\n".join(output_lines))
            emit(f"\n📄 报告已写入: {args.output}")
        except Exception as e:
            emit(f"⚠ 报告写入失败: {e}")

    # 综合退出码
    overall = 0
    if semgrep_exit > 0:
        overall |= 1
    if pylint_exit > 0:
        overall |= 2
    if mypy_exit > 0:
        overall |= 4
    return overall


# ── 辅助函数 ──────────────────────────────────────────────────────────

def _cleanup_stale_locks(max_age: int = 300):
    """清理锁目录中超过 max_age 秒的 mailbus 锁文件和 session 锁文件

    默认 max_age=300（5分钟），每次 scan 周期都会执行。
    也清理遗留的 session 级 .lock 文件和 .db-shm/.db-wal 文件。
    """
    import glob
    from .utils import get_lock_root

    now = time.time()
    lock_root = get_lock_root()

    # 清理 mailbus 锁文件
    for fpath in glob.glob(os.path.join(lock_root, "ziyan-mailbus-*.lock")):
        try:
            if now - os.path.getmtime(fpath) > max_age:
                os.unlink(fpath)
        except OSError:
            pass

    # 清理 agentmemory 残留锁文件
    for pattern in [
        os.path.join(lock_root, "agentmemory*.sock"),
        os.path.join(os.path.expanduser("~/.agentmemory"), "*.lock"),
    ]:
        for fpath in glob.glob(pattern):
            try:
                if now - os.path.getmtime(fpath) > max_age:
                    os.unlink(fpath)
            except OSError:
                pass

    # 清理 session 级 .lock 文件 + .db-shm/.db-wal 残留
    for pattern in [
        os.path.join(lock_root, "*.lock"),
        os.path.join(lock_root, "*.db-shm"),
        os.path.join(lock_root, "*.db-wal"),
    ]:
        for fpath in glob.glob(pattern):
            try:
                fname = os.path.basename(fpath).lower()
                if any(kw in fname for kw in ["session", "agent", "task", "mailbus", "hermes", "openclaw"]):
                    if now - os.path.getmtime(fpath) > max_age:
                        os.unlink(fpath)
            except OSError:
                pass

    # 清理 agent inbox 目录下的残留 .lock 文件
    data_dir = DEFAULT_DATA_DIR
    inbox_dir = os.path.join(data_dir, "inbox")
    if os.path.isdir(inbox_dir):
        for agent_dir in os.listdir(inbox_dir):
            # 安全防御：拒绝路径遍历和隐藏目录
            if agent_dir.startswith(".") or "/" in agent_dir or "\\" in agent_dir:
                continue
            agent_inbox = os.path.join(inbox_dir, agent_dir)
            if os.path.isdir(agent_inbox):
                for fname in os.listdir(agent_inbox):
                    if fname.endswith(".lock") or fname.endswith(".tmp"):
                        fpath = os.path.join(agent_inbox, fname)
                        try:
                            if now - os.path.getmtime(fpath) > max_age:
                                os.unlink(fpath)
                        except OSError:
                            pass


def _read_deepseek_key_from_openclaw_config() -> str:
    """从 openclaw.json 的 env.vars 中读取 DEEPSEEK_API_KEY"""
    candidates = [
        os.path.expanduser("~/.openclaw-data/openclaw.json"),
        os.path.expanduser("~/.openclaw/openclaw.json"),
    ]
    for oc_path in candidates:
        try:
            if os.path.isfile(oc_path):
                with open(oc_path) as f:
                    oc = json.load(f)
                key = oc.get("env", {}).get("vars", {}).get("DEEPSEEK_API_KEY", "")
                if key:
                    return key
        except Exception:
            pass
    # fallback: 从 ~/.hermes/.env 读
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.strip().split("=", 1)[1].strip("'\"")
    return ""


def cmd_recover(args) -> int:
    """recover --continue：interrupted/paused 任务同 step 重 push。"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = getattr(args, "data_dir", None) or config.get("data_dir") or DEFAULT_DATA_DIR

    action = getattr(args, "recover_action", "continue")
    task_id = getattr(args, "task_id", "") or ""
    reason = getattr(args, "reason", "") or "cli_recover"

    if action == "cancel":
        from .task_recover import apply_cancel_task
        if not task_id:
            print("✗ 需要 --task-id")
            return 1
        out = apply_cancel_task(data_dir, task_id, reason=reason)
        if out.get("ok"):
            print(f"✓ 已取消 task={task_id}")
            return 0
        print(f"✗ 取消失败: {out.get('error', out)}")
        return 1

    if action != "continue":
        print(f"✗ 未知 recover 动作: {action}（可用 continue / cancel）")
        return 1

    if not task_id:
        print("✗ recover --continue 需要 --task-id")
        return 1

    from .task_recover import recover_continue
    out = recover_continue(data_dir, task_id, reason=reason)
    if out.get("ok"):
        disp = "已 dispatch" if out.get("dispatch_ok") else "dispatch 失败（检查 inbox）"
        print(f"✓ recover continue task={task_id} step={out.get('step_id')} → {out.get('to_person')} ({disp})")
        return 0 if out.get("dispatch_ok") else 1
    print(f"✗ recover 失败: {out.get('error', out)}")
    return 1


def cmd_iteration(args) -> int:
    """三轮迭代：诊断 → 工单 → 自迭代协议"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    agents = config.get("agents", {})

    from lib.iteration_engine import run_round1, run_round2, run_round3, run_all, evaluate_round1_gate

    r = (args.round or "1").lower()
    force = getattr(args, "force", False)
    if r in ("1", "r1", "diagnosis"):
        d = run_round1(data_dir, agents)
        gate = evaluate_round1_gate(data_dir, agents)
        print(f"✓ Round1 诊断 → store/iterations/round-1-diagnosis.json")
        print(f"  问题: {d['summary']['problem_count']} | 待审计: {gate.get('pending_audit_total', 0)}")
        print(f"  主任务 {gate.get('primary_task_id')}: status={gate.get('primary_status')} audit={gate.get('primary_has_audit')}")
        if gate.get("blockers"):
            print(f"  ⛔ Round2 未解锁:")
            for b in gate["blockers"]:
                print(f"     - {b}")
        else:
            print(f"  ✅ Round1 通过，可运行 --round 2")
        return 0
    if r in ("2", "r2", "backlog"):
        d = run_round2(data_dir, agents, force=force)
        if d.get("status") == "blocked":
            print(f"⛔ Round2 被门禁拦截（加 --force 可跳过）")
            for b in d.get("blockers", []):
                print(f"   - {b}")
            return 1
        print(f"✓ Round2 工单 → store/iterations/round-2-backlog.json ({len(d.get('items', []))} 条)")
        for item in d.get("items", [])[:8]:
            print(f"  {item['id']} [{item['priority']}] {item['owner']}: {item['title'][:50]}")
        return 0
    if r in ("3", "r3", "protocol"):
        p = run_round3(data_dir, agents, force=force)
        if p.get("status") == "blocked":
            print(f"⛔ Round3 跳过: {p.get('reason')}")
            return 1
        print(f"✓ Round3 协议 → store/iterations/round-3-protocol.json")
        st = p.get("backlog_status", {})
        print(f"  backlog: done={st.get('done', 0)} pending={st.get('pending', 0)}")
        return 0
    if r in ("all", "full"):
        result = run_all(data_dir, agents, force=force)
        print("✓ 迭代结果:")
        print(f"  Round1: {result['round1']}")
        print(f"  Round1 gate: unlocked={result['round2_unlocked']}")
        print(f"  Round2: {result.get('round2', {})}")
        print(f"  Round3: {result.get('round3', {})}")
        return 0 if result.get("round2_unlocked") or force else 1
    print(f"✗ 未知 round: {args.round}（可用 1/2/3/all）")
    return 1


def _find_config(args) -> str:
    """获取配置文件路径"""
    data_dir = getattr(args, 'data_dir', None)
    if data_dir:
        return f"{data_dir}/config.json"
    
    # 先从默认路径找
    default_path = f"{DEFAULT_CONFIG['data_dir']}/config.json"
    if os.path.exists(default_path):
        return default_path
    
    # 尝试从当前目录找
    local_path = "store/config.json"
    if os.path.exists(local_path):
        return local_path
    
    # 返回默认路径
    return default_path


# ── CLI 参数解析 ──────────────────────────────────────────────────────

def _add_data_dir_arg(p):
    """给子命令添加 --data-dir 参数"""
    p.add_argument("--data-dir", default=None, help="数据目录路径（覆盖默认）")

