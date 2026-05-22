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

import sys
import os
import json
import argparse

# 确保 lib 在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.models import (
    Message, MsgStatus, Priority, MsgType, Inbox, AgentConfig, BusConfig,
)
from lib.utils import (
    json_read, json_write, jsonl_append, log_error, resolve_paths,
    build_message, _now_iso, _ensure_dir, file_lock,
)
from lib.scanner import build_queues, update_message_status
from lib.pusher import push_messages, resolve_cli_chain
from lib.ack_handler import scan_ack_files, scan_forward_files
from lib.archiver import archive_all


# ── 配置加载 ──────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "project": "ziyan-mailbus",
    "version": "1.0.0",
    "data_dir": "/mnt/e/ai_tools/mail/store",
    "ack_timeout": 30,
    "max_retries": 3,
    "archive_days": 7,
    "archive_max_messages": 300,
    "agents": {},
}


def load_config(config_path: str) -> dict:
    """加载配置，缺失字段用默认值填充"""
    config = json_read(config_path, {})
    for k, v in DEFAULT_CONFIG.items():
        config.setdefault(k, v)
    return config


def save_config(config_path: str, config: dict):
    """保存配置"""
    json_write(config_path, config)


def get_system_message(agent_name: str) -> dict:
    """生成新 agent 上线时的系统消息"""
    return {
        "id": f"sys-welcome-{agent_name}",
        "from": "mailbus",
        "to": agent_name,
        "priority": "urgent",
        "type": "system",
        "content": f"欢迎 {agent_name} 加入 ziyan-mailbus 消息总线。",
        "reply_format": {
            "ack": {
                "file": f"/mnt/e/ai_tools/mail/store/inbox/{agent_name}/ack.json",
                "format": {"action": "ack", "msg_id": "<id>", "agent": agent_name, "timestamp": "<ISO时间>"},
            },
            "mark_read": {
                "format": {"action": "mark_read", "msg_ids": ["<id>"], "agent": agent_name, "timestamp": "<ISO时间>"},
            },
            "forward": {
                "target_format": "/mnt/e/ai_tools/mail/store/inbox/<目标agent>/inbox.json",
                "format": {
                    "action": "forward", "original_msg_id": "<id>", "from": agent_name,
                    "to": "<目标>", "type": "normal", "priority": "normal",
                    "content": "...", "attachments": [], "timestamp": "<ISO时间>",
                },
            },
        },
        "system_info": {
            "inbox_location": f"/mnt/e/ai_tools/mail/store/inbox/{agent_name}/inbox.json",
            "inbox_format": "/mnt/e/ai_tools/mail/store/inbox/<目标agent>/inbox.json",
            "registered_agents": [],
            "bus_cli_location": "/mnt/e/ai_tools/mail/bus.py",
            "bus_cron_interval": "每分钟扫描一次",
            "ack_timeout": "30秒",
        },
        "status": MsgStatus.PENDING,
        "created_at": _now_iso(),
    }


# ── CLI 命令实现 ──────────────────────────────────────────────────────

def cmd_init(args):
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


def cmd_scan(args):
    """扫描全员 inbox → 推送未读消息"""
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
        )
        all_failed.extend(failed)
        
        if failed:
            print(f"     ✗ {len(failed)} 条推送失败")
        else:
            print(f"     ✓ 全部送达")
    
    return all_failed


def cmd_send(args):
    """手动发消息给指定 agent"""
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
    
    if to not in agents:
        print(f"✗ agent '{to}' 未注册")
        print(f"  已注册: {', '.join(agents.keys())}")
        return 1
    
    agent_types = config.get("agent_types", {})
    cli_cmds = [c[0] for c in resolve_cli_chain(agents[to], agent_types)]
    
    print(f"  CLI: {' | '.join(cli_cmds[:3]) or '(纯文件通信)'}")
    
    # 构建消息
    msg = build_message(from_, to, content, msg_type, priority)
    
    # 写入 inbox
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{to}/inbox.json"
    inbox_data = json_read(inbox_file, {"agent": to, "has_unread": False, "messages": [], "since": _now_iso()})
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg.to_dict())
    json_write(inbox_file, inbox.to_dict())
    
    print(f"✓ 消息已写入 {to} 的 inbox")
    print(f"  ID: {msg.id}")
    print(f"  内容: {content[:60]}{'...' if len(content) > 60 else ''}")
    print(f"  下个 cron 周期将自动推送")
    return 0


def cmd_broadcast(args):
    """发公告板（推送全员）"""
    config_path = _find_config(args)
    config = load_config(config_path)
    data_dir = config["data_dir"]
    agents = config.get("agents", {})
    
    if not agents:
        print("✗ 没有注册的 agent")
        return 1
    
    content = args.msg
    priority = getattr(args, 'priority', Priority.NORMAL)
    
    # 写入公告板
    paths = resolve_paths(data_dir)
    board_data = json_read(paths["board"], {"board": [], "created_at": _now_iso()})
    
    board_msg = {
        "id": f"board-{_now_iso()[:10]}-{len(board_data['board']) + 1}",
        "content": content,
        "priority": priority,
        "created_at": _now_iso(),
    }
    board_data["board"].append(board_msg)
    json_write(paths["board"], board_data)
    
    # 写入每个 agent 的 inbox
    from_ = "broadcast"
    for name in agents:
        msg = build_message(from_, name, content, MsgType.NOTICE, priority)
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {"agent": name, "has_unread": False, "messages": [], "since": _now_iso()})
        inbox = Inbox.from_dict(inbox_data)
        inbox.has_unread = True
        inbox.messages.append(msg.to_dict())
        json_write(inbox_file, inbox.to_dict())
    
    print(f"✓ 公告已发送给 {len(agents)} 个 agent")
    return 0


def cmd_ack(args):
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


def cmd_mark_read(args):
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


def cmd_status(args):
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
            if isinstance(m, dict):
                print(f"  [{m['status']}] {m['id']} — {m.get('content', '')[:40]}")
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
            if isinstance(m, dict):
                s = m.get("status", "unknown")
                statuses[s] = statuses.get(s, 0) + 1
        
        parts = [f"{s}: {c}" for s, c in sorted(statuses.items())]
        print(f"  {name}: {', '.join(parts) if parts else '空'}")
    
    return 0


def cmd_retry(args):
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
                if isinstance(m, dict) and m.get("id") == args.msg_id:
                    m["status"] = MsgStatus.PENDING
                    m["pushed_count"] = 0
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
            if isinstance(m, dict) and m.get("status") == MsgStatus.FAILED:
                m["status"] = MsgStatus.PENDING
                m["pushed_count"] = 0
                m["status"] = MsgStatus.RESENDING
                changed = True
                count += 1
        if changed:
            json_write(inbox_file, inbox.to_dict())
    
    print(f"✓ 重置了 {count} 条失败消息为待重试")
    if count > 0:
        print("  运行 bus.py scan 即可重新推送")
    return 0


def cmd_archive(args):
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


def cmd_errors(args):
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


def cmd_agent_add(args):
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


def cmd_agent_remove(args):
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


# ── 辅助函数 ──────────────────────────────────────────────────────────

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


def main():
    parser = argparse.ArgumentParser(description="ziyan-mailbus — 多 Agent 消息总线")
    
    sub = parser.add_subparsers(dest="command", help="可用命令")
    
    # init
    p_init = sub.add_parser("init", help="初始化目录结构")
    _add_data_dir_arg(p_init)
    
    # scan
    p_scan = sub.add_parser("scan", help="扫描全员 inbox 并推送")
    _add_data_dir_arg(p_scan)
    
    # send
    p_send = sub.add_parser("send", help="手动发消息")
    _add_data_dir_arg(p_send)
    p_send.add_argument("agent", help="目标 agent 名称")
    p_send.add_argument("--msg", required=True, help="消息内容")
    p_send.add_argument("--from", dest="from_", default="manual", help="发件人")
    p_send.add_argument("--priority", default="normal", choices=["normal", "urgent"])
    p_send.add_argument("--type", default="notice", choices=["task", "notice", "question", "system"])
    
    # broadcast
    p_bc = sub.add_parser("broadcast", help="发公告板")
    _add_data_dir_arg(p_bc)
    p_bc.add_argument("--msg", required=True, help="公告内容")
    p_bc.add_argument("--priority", default="normal", choices=["normal", "urgent"])
    
    # ack
    p_ack = sub.add_parser("ack", help="agent 确认收到")
    _add_data_dir_arg(p_ack)
    p_ack.add_argument("--msg-id", required=True, help="消息 ID")
    p_ack.add_argument("--agent", required=True, help="agent 名称")
    
    # mark-read
    p_mr = sub.add_parser("mark-read", help="agent 标记已读")
    _add_data_dir_arg(p_mr)
    p_mr.add_argument("--msg-ids", required=True, help="消息 ID 列表（逗号分隔）")
    p_mr.add_argument("--agent", required=True, help="agent 名称")
    
    # status
    p_st = sub.add_parser("status", help="查看消息状态")
    _add_data_dir_arg(p_st)
    p_st.add_argument("--agent", help="指定 agent")
    p_st.add_argument("--failed", action="store_true", help="查看失败消息")
    
    # retry
    p_rt = sub.add_parser("retry", help="重试失败消息")
    _add_data_dir_arg(p_rt)
    p_rt.add_argument("--msg-id", help="指定消息 ID（不指定则重试全部）")
    
    # archive
    p_ar = sub.add_parser("archive", help="手动触发归档")
    _add_data_dir_arg(p_ar)
    
    # errors
    p_er = sub.add_parser("errors", help="查看错误日志")
    _add_data_dir_arg(p_er)
    
    # agent-add
    p_aa = sub.add_parser("agent-add", help="注册新 agent")
    _add_data_dir_arg(p_aa)
    p_aa.add_argument("agent", help="agent 名称")
    p_aa.add_argument("--type", default="none", choices=["hermes", "hermes_profile", "openclaw", "cline", "opencode", "none"], help="agent 类型")
    p_aa.add_argument("--role", default="", help="角色说明")
    p_aa.add_argument("--profile", default=None, help="Hermes profile 名称（仅 hermes_profile 类型）")
    p_aa.add_argument("--agent-id", default=None, help="OpenClaw agent ID（仅 openclaw 类型）")
    
    # agent-remove
    p_ar = sub.add_parser("agent-remove", help="移除 agent")
    _add_data_dir_arg(p_ar)
    p_ar.add_argument("agent", help="agent 名称")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # 转发 --data-dir
    cmd_map = {
        "init": cmd_init,
        "scan": cmd_scan,
        "send": cmd_send,
        "broadcast": cmd_broadcast,
        "ack": cmd_ack,
        "mark-read": cmd_mark_read,
        "status": cmd_status,
        "retry": cmd_retry,
        "archive": cmd_archive,
        "errors": cmd_errors,
        "agent-add": cmd_agent_add,
        "agent-remove": cmd_agent_remove,
    }
    
    return cmd_map[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
