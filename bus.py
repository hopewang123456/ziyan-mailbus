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
from pathlib import Path
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.utils import configure_stdio_utf8

configure_stdio_utf8()

from lib.models import (
    Message, MsgStatus, Priority, MsgType, Inbox, AgentConfig, BusConfig,
)
from lib.utils import (
    json_read, json_write, jsonl_append, log_error, resolve_paths,
    build_message, _now_iso, _ensure_dir, file_lock,
)
from lib.scanner import build_queues, run_housekeeping, update_message_status
from lib.pusher import push_messages, resolve_cli_chain
from lib.ack_handler import scan_ack_files, scan_forward_files, scan_error_reports
from lib.archiver import archive_all
from lib.tracker import TaskTracker
from lib.heartbeat import heartbeat_scan, is_online, load_status
from lib.search import scan_and_index, search
from lib import api as api_serve
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



from lib.commands import load_config, save_config, cmd_init, cmd_scan, cmd_search, cmd_heartbeat, cmd_serve, cmd_send, cmd_broadcast, cmd_ack, cmd_mark_read, cmd_status, cmd_retry, cmd_archive, cmd_backup, cmd_errors, cmd_agent_add, cmd_agent_remove, cmd_review, cmd_launch, cmd_iteration, cmd_recover, _add_data_dir_arg


def main():
    parser = argparse.ArgumentParser(description="ziyan-mailbus — 多 Agent 消息总线")
    
    sub = parser.add_subparsers(dest="command", help="可用命令")
    
    # init
    p_init = sub.add_parser("init", help="初始化目录结构（--fresh 从 access/org/config 重建）")
    _add_data_dir_arg(p_init)
    p_init.add_argument(
        "--fresh",
        action="store_true",
        help="清空并重建 store（聚合 config/ + org/ + access/agent.json）",
    )
    
    # scan
    p_scan = sub.add_parser("scan", help="扫描全员 inbox 并推送")
    _add_data_dir_arg(p_scan)
    
    # send
    p_send = sub.add_parser("send", help="手动发消息")
    _add_data_dir_arg(p_send)
    p_send.add_argument("agent", nargs="?", default=None, help="目标 agent 名称（不传则用 --domain）")
    p_send.add_argument("--msg", required=True, help="消息内容")
    p_send.add_argument("--from", dest="from_", default="manual", help="发件人")
    p_send.add_argument("--priority", default="normal", choices=["normal", "urgent"])
    p_send.add_argument("--type", default="notice", choices=list(MsgType.ALL), help="消息类型")
    p_send.add_argument("--forward-to", nargs="*", default=[], help="转发目标 agent（可多个）")
    p_send.add_argument("--domain", default="", help="按 domain 路由（如 engineering），不指定则按 agent 名称发送")
    p_send.add_argument("--project", default="", help="所属项目（如 mailbus）")
    
    # broadcast
    p_bc = sub.add_parser("broadcast", help="发公告板")
    _add_data_dir_arg(p_bc)
    p_bc.add_argument("--msg", required=True, help="公告内容")
    p_bc.add_argument("--priority", default="normal", choices=["normal", "urgent"])
    p_bc.add_argument("--domain", default="", help="限定 domain（如 engineering），不指定则广播全员")
    
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
    
    # review
    p_rv = sub.add_parser("review", help="运行代码审查（review.py）")
    _add_data_dir_arg(p_rv)
    p_rv.add_argument("--workdir", default="", help="工作目录（默认当前目录）")
    p_rv.add_argument("--commit", default="", help="审查指定 commit（如 HEAD）")
    p_rv.add_argument("--semgrep", action="store_true", help="同时跑 Semgrep 扫描")
    p_rv.add_argument("--output", default="", help="输出报告路径")
    p_rv.add_argument("--target", default=".", help="Semgrep 目标目录")
    
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
    
    # heartbeat
    p_hb = sub.add_parser("heartbeat", help="心跳检测（检测所有 agent 在线状态）")
    _add_data_dir_arg(p_hb)
    
    # launch (启动/停止 agent 进程)
    p_lc = sub.add_parser("launch", help="启动/停止/查看 agent 常驻进程")
    _add_data_dir_arg(p_lc)
    p_lc.add_argument("--agent", default="", help="指定 agent（不指定则操作全部）")
    p_lc.add_argument("--stop", action="store_true", help="停止所有 agent 进程")
    p_lc.add_argument("--status", action="store_true", help="查看运行状态")

    # serve (HTTP API)
    p_sv = sub.add_parser("serve", help="启动 HTTP API 服务（用于 Web 看板）")
    _add_data_dir_arg(p_sv)
    p_sv.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    p_sv.add_argument("--port", type=int, default=None, help="监听端口（默认见 lib.constants.DEFAULT_API_PORT）")
    p_sv.add_argument("--token", default="", help="API 认证 token（留空不启用认证）")
    
    # backup
    p_bk = sub.add_parser("backup", help="备份 store/ 目录到 backup/（tar.gz，保留最近7个）")
    _add_data_dir_arg(p_bk)
    
    # search
    p_sr = sub.add_parser("search", help="消息全文检索")
    _add_data_dir_arg(p_sr)
    p_sr.add_argument("--query", default="", help="搜索关键词（FTS5 语法）")
    p_sr.add_argument("--scope", default="messages", choices=["messages", "catalog", "all"],
                      help="messages=仅消息 catalog=外部工具/目录 all=两者")
    p_sr.add_argument("--from", dest="from_agent", default="", help="按发件人过滤")
    p_sr.add_argument("--to", dest="to_agent", default="", help="按收件人过滤")
    p_sr.add_argument("--type", default="", help="按消息类型过滤")
    p_sr.add_argument("--status", default="", help="按状态过滤")
    p_sr.add_argument("--limit", type=int, default=20, help="最大返回条数")

    # iteration — 三轮自迭代
    p_it = sub.add_parser("iteration", help="三轮迭代：诊断→工单→协议")
    _add_data_dir_arg(p_it)
    p_it.add_argument("--round", default="1", help="1|2|3|all（默认 1，仅诊断）")
    p_it.add_argument("--force", action="store_true", help="跳过 Round1 门禁（调试用）")

    # recover — 断链恢复 / 取消
    p_rc = sub.add_parser("recover", help="任务恢复（--continue）或取消（--cancel）")
    _add_data_dir_arg(p_rc)
    p_rc.add_argument("recover_action", nargs="?", default="continue",
                      choices=["continue", "cancel"], help="continue=同 step 重 push；cancel=取消任务")
    p_rc.add_argument("--task-id", required=False, help="任务 ID")
    p_rc.add_argument("--reason", default="", help="操作原因（写入 fsm history）")
    
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
        "backup": cmd_backup,
        "errors": cmd_errors,
        "agent-add": cmd_agent_add,
        "agent-remove": cmd_agent_remove,
        "heartbeat": cmd_heartbeat,
        "serve": cmd_serve,
        "search": cmd_search,
        "review": cmd_review,
        "launch": cmd_launch,
        "iteration": cmd_iteration,
        "recover": cmd_recover,
    }
    
    return cmd_map[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
