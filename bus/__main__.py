#!/usr/bin/env python3
"""`python -m bus` CLI 入口。"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lib.application.commands.commands import (  # noqa: E402
    _add_data_dir_arg,
    cmd_ack,
    cmd_agent_add,
    cmd_agent_remove,
    cmd_archive,
    cmd_backup,
    cmd_broadcast,
    cmd_errors,
    cmd_heartbeat,
    cmd_init,
    cmd_iteration,
    cmd_launch,
    cmd_mark_read,
    cmd_recover,
    cmd_retry,
    cmd_review,
    cmd_scan,
    cmd_search,
    cmd_send,
    cmd_serve,
    cmd_status,
)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bus", description="ziyan-mailbus CLI")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="初始化 store")
    _add_data_dir_arg(p)
    p.add_argument("--fresh", action="store_true", help="从 SoT 重建 store")
    p.add_argument("--merge", action="store_true", help="合并 SoT override 到已有 store/config.json")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("scan", help="扫描 inbox 并推送")
    _add_data_dir_arg(p)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("search", help="消息/目录检索")
    p.add_argument("query", nargs="?", default="", help="检索词")
    _add_data_dir_arg(p)
    p.add_argument("--scope", choices=("messages", "catalog", "all"), default="messages")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--from-agent", dest="from_agent", default="")
    p.add_argument("--to-agent", dest="to_agent", default="")
    p.add_argument("--type", default="")
    p.add_argument("--status", default="")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("heartbeat", help="心跳与健康检查")
    _add_data_dir_arg(p)
    p.set_defaults(func=cmd_heartbeat)

    p = sub.add_parser("serve", help="启动 HTTP API")
    _add_data_dir_arg(p)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--token", default="")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("launch", help="启动/停止 agent 常驻进程")
    _add_data_dir_arg(p)
    p.add_argument("--agent", default="")
    p.add_argument("--stop", action="store_true")
    p.add_argument("--status", action="store_true")
    p.set_defaults(func=cmd_launch)

    p = sub.add_parser("send", help="发送消息")
    p.add_argument("agent", nargs="?", default="")
    _add_data_dir_arg(p)
    p.add_argument("--msg", "--content", dest="msg", required=True)
    p.add_argument("--from", dest="from_", default=None)
    p.add_argument("--priority", default="normal")
    p.add_argument("--type", default="notice")
    p.add_argument("--domain", default="")
    p.add_argument("--project", default="")
    p.add_argument("--forward-to", dest="forward_to", default=None)
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("broadcast", help="发公告板")
    _add_data_dir_arg(p)
    p.add_argument("--msg", required=True)
    p.add_argument("--priority", default="normal")
    p.add_argument("--domain", default="")
    p.set_defaults(func=cmd_broadcast)

    p = sub.add_parser("ack", help="确认收到消息")
    _add_data_dir_arg(p)
    p.add_argument("--msg-id", required=True)
    p.add_argument("--agent", required=True)
    p.set_defaults(func=cmd_ack)

    p = sub.add_parser("mark-read", help="标记已读")
    _add_data_dir_arg(p)
    p.add_argument("--msg-ids", required=True)
    p.add_argument("--agent", required=True)
    p.set_defaults(func=cmd_mark_read)

    p = sub.add_parser("status", help="查看消息状态")
    _add_data_dir_arg(p)
    p.add_argument("--agent", default="")
    p.add_argument("--failed", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("retry", help="重试失败消息")
    _add_data_dir_arg(p)
    p.add_argument("--msg-id", default="")
    p.set_defaults(func=cmd_retry)

    p = sub.add_parser("archive", help="手动归档")
    _add_data_dir_arg(p)
    p.set_defaults(func=cmd_archive)

    p = sub.add_parser("backup", help="备份 store")
    _add_data_dir_arg(p)
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("errors", help="查看错误日志")
    _add_data_dir_arg(p)
    p.set_defaults(func=cmd_errors)

    p = sub.add_parser("agent-add", help="注册 agent")
    p.add_argument("agent")
    _add_data_dir_arg(p)
    p.add_argument("--type", default="none")
    p.add_argument("--role", default="")
    p.add_argument("--agent-id", default=None)
    p.add_argument("--profile", default=None)
    p.add_argument("--cli", default="")
    p.set_defaults(func=cmd_agent_add)

    p = sub.add_parser("agent-remove", help="移除 agent")
    p.add_argument("agent")
    _add_data_dir_arg(p)
    p.set_defaults(func=cmd_agent_remove)

    p = sub.add_parser("review", help="代码审查")
    _add_data_dir_arg(p)
    p.add_argument("--workdir", default="")
    p.add_argument("--commit", default="")
    p.add_argument("--output", default="")
    p.add_argument("--target", default="")
    p.add_argument("--semgrep", action="store_true")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("recover", help="任务 recover continue/cancel")
    p.add_argument("recover_action", choices=("continue", "cancel"))
    _add_data_dir_arg(p)
    p.add_argument("--task-id", default="")
    p.add_argument("--reason", default="")
    p.set_defaults(func=cmd_recover)

    p = sub.add_parser("iteration", help="三轮迭代")
    _add_data_dir_arg(p)
    p.add_argument("--round", default="1")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_iteration)

    return ap


def main(argv: list[str] | None = None) -> int:
    from lib.infra.env_bootstrap import load_mailbus_env
    from lib.infra.utils import configure_stdio_utf8

    configure_stdio_utf8()
    load_mailbus_env()
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
