#!/usr/bin/env python3
"""
ziyan-mailbus — 多 Agent 消息总线系统

用法:
  bus.py init                        初始化目录结构 + 写默认配置
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

配置: data_dir (默认 /mnt/e/ai_tools/mail/store) 中的 config.json
"""

import os
import sys
import json
import argparse
import time
import shutil
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
from lib.pusher import push_messages, resolve_cli_chain
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
    for k, v in DEFAULT_CONFIG.items():
        config.setdefault(k, v)
    # 校验配置合法性
    errors = validate_config(config)
    if errors:
        print(f"⚠️ 配置校验告警 ({config_path}):")
        for err in errors:
            print(f"   - {err}")
    return config


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
    """初始化目录结构 + 创建默认配置"""
    data_dir = args.data_dir or DEFAULT_CONFIG["data_dir"]
    _ensure_dir(data_dir)
    config_path = f"{data_dir}/config.json"
    
    # 如果已经有配置，不覆盖
    existing = json_read(config_path, None)
    if existing:
        print(f"✗ 配置已存在: {config_path}")
        print("  如需重新初始化，请先删除该文件")
        return 1
    
    config = dict(DEFAULT_CONFIG)
    config["data_dir"] = data_dir
    
    # 创建目录结构
    _ensure_dir(f"{data_dir}/inbox")
    _ensure_dir(f"{data_dir}/queue/urgent")
    _ensure_dir(f"{data_dir}/queue/normal")
    _ensure_dir(f"{data_dir}/archive")
    _ensure_dir(f"{data_dir}/errors")
    
    # 写配置
    save_config(config_path, config)
    
    # 写空 sent.json 和 board.json
    json_write(f"{data_dir}/sent.json", {})
    json_write(f"{data_dir}/board.json", {
        "board": [],
        "created_at": _now_iso(),
    })
    
    print(f"✓ ziyan-mailbus 已初始化")
    print(f"  数据目录: {data_dir}")
    print(f"  配置文件: {config_path}")
    print(f"\n下一步: 用 bus.py agent-add 注册你的 agent")
    return 0


def cmd_scan(args) -> int:
    """扫描全员 inbox → 推送未读消息"""
    # 清理过期锁文件（超过1小时），防止 /tmp 积压
    _cleanup_stale_locks()

    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    agents = config.get("agents", {})
    
    if not agents:
        print("✗ 没有注册的 agent，先用 bus.py agent-add 注册")
        return 1
    
    # 1. 先处理所有 agent 的回复（ack / mark_read / forward）
    ack_count = scan_ack_files(data_dir, agents)
    fwd_count = scan_forward_files(data_dir, agents)
    if ack_count:
        print(f"✓ 处理了 {ack_count} 条 ack")
    if fwd_count:
        print(f"✓ 处理了 {fwd_count} 条转发")
    
    # 2. 扫描 inbox → 构建队列
    urgent_queue, normal_queue = build_queues(data_dir, agents)
    
    # 2b. 执行运维任务（超时催办 / 技能消费 / 离线检测 / 归档 / 索引）
    run_housekeeping(data_dir, agents)
    
    total_messages = sum(len(v) for v in urgent_queue.values()) + sum(len(v) for v in normal_queue.values())
    if total_messages == 0:
        print("✓ 全员已读，无新消息")
        return 0
    
    print(f"📬 发现 {total_messages} 条待推送消息")
    if urgent_queue:
        print(f"   ⚡ 加急: {sum(len(v) for v in urgent_queue.values())} 条")
    if normal_queue:
        print(f"   📨 普通: {sum(len(v) for v in normal_queue.values())} 条")
    
    # 3. 先推加急队列
    # 如果有加急消息，对应的普通消息先跳过（被抢占）
    preempted = set()
    if urgent_queue:
        # 找出既在 urgent 又在 normal 的 agent
        for agent_name in urgent_queue:
            if agent_name in normal_queue:
                preempted.add(agent_name)
                preempted_count = len(normal_queue[agent_name])
                print(f"   ⚡ {agent_name}: {preempted_count} 条普通消息被加急抢占")
                del normal_queue[agent_name]

    failed_urgent = _push_queue(data_dir, config, urgent_queue, "加急")
    failed_normal = _push_queue(data_dir, config, normal_queue, "普通")
    
    all_failed = failed_urgent + failed_normal
    if all_failed:
        print(f"\n⚠  推送失败: {len(all_failed)} 条（已记录错误日志）")
        for fid in all_failed[:5]:
            print(f"   ✗ {fid}")
        if len(all_failed) > 5:
            print(f"   ... 还有 {len(all_failed) - 5} 条")
    else:
        print(f"\n✓ 全部推送完成")
    
    # 4. 错误回执处理
    reports = scan_error_reports(data_dir, agents)
    if reports:
        print(f"\n📕 错误回执: {len(reports)} 条")
        for r in reports:
            tracker.update_status(r['task_id'], 'failed',
                                  {"code": r['error_code'], "reason": r['reason']})
            print(f"   → {r['task_id']}: [{r['error_code']}] {r['reason'][:60]}")

    # 5. 心跳检测
    heartbeat_interval = config.get("heartbeat_interval", 300)
    hb_changes = heartbeat_scan(agents, config.get("agent_types", {}), data_dir, config=config,
                                 interval=heartbeat_interval)
    if hb_changes:
        for c in hb_changes:
            if c.get("type") == "health":
                print(f"   🔄 AgentMemory: {c['old_status']} → {c['new_status']}")
            else:
                icon = "🟢" if c["new_status"] == "online" else "🔴"
                print(f"   {icon} 心跳 {c['agent']}: {c['old_status']} → {c['new_status']}")
    
    # 健康状态摘要（每轮 scan 显示一次）
    hb_status = load_status(data_dir)
    health = hb_status.get("health", {})
    am = health.get("agentmemory", {})
    if am.get("status") == "unreachable":
        print(f"   ⚠️ AgentMemory 不可用")
    inbox_warnings = health.get("inbox_warnings", [])
    if inbox_warnings:
        for w in inbox_warnings[:3]:
            print(f"   ⚠️ {w['agent']}: inbox {w['count']} 条消息积压")

    # 6. 催办检查
    tracker = TaskTracker(data_dir)
    reminder_minutes = config.get("reminder_minutes", 5)
    max_reminders = config.get("max_reminders", 3)
    escalated = tracker.check_reminders(agents, reminder_minutes, max_reminders)
    if escalated:
        print(f"\n⏰ 催办: {len(escalated)} 条任务超时")
        for e in escalated:
            print(f"   → {e['task_id']}: {e['summary'][:40]} ({e['reminded_count']}/{max_reminders})")
            if e['reminded_count'] >= max_reminders:
                tracker.update_status(e['task_id'], 'timeout',
                                      {"code": "TIMEOUT", "reason": f"超过{max_reminders}次催办未响应"})
    
    # 7. 消息索引
    scan_and_index(data_dir, agents)

    return 0


def cmd_search(args) -> int:
    """消息检索"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]

    results = search(
        data_dir,
        query_str=getattr(args, 'query', ''),
        from_agent=getattr(args, 'from_agent', ''),
        to_agent=getattr(args, 'to_agent', ''),
        msg_type=getattr(args, 'type', ''),
        status=getattr(args, 'status', ''),
        limit=getattr(args, 'limit', 20),
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
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    agents = config.get("agents", {})
    agent_types = config.get("agent_types", {})
    port = getattr(args, 'port', 9812)

    if not agents:
        print("✗ 没有注册的 agent")
        return 1

    token = getattr(args, 'token', '')
    api_serve(data_dir, agents, agent_types, host=args.host, port=port, token=token)
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
            failed = push_via_webhook(
                data_dir=data_dir,
                agent_name=agent_name,
                messages=messages,
                webhook_url=webhook_url,
                webhook_secret=agent_cfg.get("webhook_secret", ""),
                max_retries=config.get("max_retries", 3),
                auto_ack=agent_cfg.get("type") in ("hermes", "hermes_profile"),
            )
        else:
            chain = resolve_cli_chain(agent_cfg, agent_types)
            cli_cmds = [c[0] for c in chain]  # 只取命令，不要别名
            print(f"   → {agent_name} ({label}): {len(messages)} 条" + (f' [{len(cli_cmds)} models]' if len(cli_cmds) > 1 else ''))
            
            failed = push_messages(
                data_dir=data_dir,
                agent_name=agent_name,
                messages=messages,
                cli_cmd=cli_cmds,
                ack_timeout=config.get("ack_timeout", 30),
                max_retries=config.get("max_retries", 3),
                auto_ack=agent_cfg.get("type") in ("hermes", "hermes_profile"),  # Hermes 类型直接标记已读，其他靠回复确认
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
                    tracker.create(task_id=msg.id, summary=content[:80], assignee=target)
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
    _write_to_inbox(data_dir, to, msg)
    if msg_type in (MsgType.TASK, MsgType.TASK_REPLY):
        try:
            tracker.create(task_id=msg.id, summary=content[:80], assignee=to)
        except Exception as e:
            print(f"  ⚠️ 任务追踪创建失败: {e}")
    print(f"✓ 消息已写入 {to} 的 inbox")
    print(f"  ID: {msg.id}")
    print(f"  内容: {content[:60]}{'...' if len(content) > 60 else ''}")
    if project:
        print(f"  项目: {project}")
    print(f"  下个 cron 周期将自动推送")
    return 0


def _write_to_inbox(data_dir: str, agent_name: str, msg: Message):
    """将消息写入指定 agent 的 inbox"""
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent_name}/inbox.json"
    inbox_data = json_read(inbox_file, {"agent": agent_name, "has_unread": False, "messages": [], "since": _now_iso()})
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg.to_dict())
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
    
    results = archive_all(data_dir, agents, config.get("archive_days", 7), config.get("archive_max_messages", 300))
    
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
    """代码审查：运行 review.py 审查代码变更"""
    import subprocess

    review_script = "/mnt/e/ai_tools/pr-agent/review.py"
    if not os.path.isfile(review_script):
        print(f"✗ review.py 未找到: {review_script}")
        return 1

    workdir = args.workdir or os.getcwd()
    if not os.path.isdir(workdir):
        print(f"✗ 目录不存在: {workdir}")
        return 1

    cmd = [sys.executable, review_script]
    if args.commit:
        cmd += ["--commit", args.commit]
    if args.semgrep:
        cmd += ["--semgrep"]
    if args.output:
        cmd += ["--output", args.output]
    if args.target:
        cmd += ["--target-dir", args.target]

    print(f"🔍 代码审查开始: {workdir}")
    env = os.environ.copy()
    env["DEEPSEEK_API_KEY"] = env.get("DEEPSEEK_API_KEY", "")
    if not env["DEEPSEEK_API_KEY"]:
        print("⚠ DEEPSEEK_API_KEY 未设置，尝试从 .env 读取...")
        env_path = os.path.expanduser("~/.hermes/.env")
        if os.path.isfile(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("DEEPSEEK_API_KEY="):
                        env["DEEPSEEK_API_KEY"] = line.strip().split("=", 1)[1].strip("'\"")
                        break

    try:
        r = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, text=True, timeout=180)
        print(r.stdout)
        if r.stderr:
            print(f"⚠ stderr: {r.stderr[:300]}")
        return r.returncode
    except subprocess.TimeoutExpired:
        print("✗ 审查超时（180秒）")
        return 1
    except Exception as e:
        print(f"✗ 审查失败: {e}")
        return 1


# ── 辅助函数 ──────────────────────────────────────────────────────────

def _cleanup_stale_locks(max_age: int = 3600):
    """清理 /tmp 中超过 max_age 秒的 mailbus 锁文件"""
    import glob
    now = time.time()
    for fpath in glob.glob("/tmp/ziyan-mailbus-*.lock"):
        try:
            if now - os.path.getmtime(fpath) > max_age:
                os.unlink(fpath)
        except OSError:
            pass


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

