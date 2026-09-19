#!/usr/bin/env python3
"""mailbus 消息总线 CLI（`mailbus` / `python -m bus` 共用入口）。

这是 README 快速开始与 AGENTS.md 快速命令里 `mailbus init / send / ack /
scan / status / serve …` 的实现。运维编排类子命令（start / stop / doctor /
portproxy …）在另一个入口：`mailbus-ops`（tools/mailbus.py）。
"""
from __future__ import annotations

import argparse
import os
import sys

# 仓库内直接运行（未 pip install）时把仓库根加入 sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

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
    cmd_result,
    cmd_retry,
    cmd_review,
    cmd_scan,
    cmd_search,
    cmd_send,
    cmd_serve,
    cmd_status,
    cmd_task_from_template,
    cmd_test_connection,
    cmd_dlq,
    cmd_demo,
    cmd_stations,
    cmd_tokens,
)


def build_parser(prog: str = "mailbus") -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=prog, description="mailbus CLI")
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
    p.add_argument("--query", dest="query_opt", default="", help="检索词（同位置参数）")
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
    p.add_argument("msg_id_pos", nargs="?", help="消息 ID（同 --msg-id）")
    p.add_argument("--msg-id", dest="msg_id")
    p.add_argument("--agent", required=True)
    p.set_defaults(func=cmd_ack)

    p = sub.add_parser("mark-read", help="标记已读")
    _add_data_dir_arg(p)
    p.add_argument("--msg-ids", required=True)
    p.add_argument("--agent", required=True)
    p.set_defaults(func=cmd_mark_read)

    p = sub.add_parser("result", help="提交工单执行回执（step-result）")
    _add_data_dir_arg(p)
    p.add_argument("task_id", help="任务 ID")
    p.add_argument("--step", dest="step_id", required=True, help="步骤 ID（如 s1）")
    p.add_argument("--agent", required=True, help="回执的 agent（需与该步 assignee 一致）")
    p.add_argument("--conclusion", default="done",
                   choices=("done", "pass", "approved", "fail", "blocked", "warning", "rejected", "need_research"),
                   help="结论（done/pass/approved 视为成功）")
    p.add_argument("--text", default="", help="结果摘要")
    p.add_argument("--artifact", default="", help="产物文件路径（可选）")
    p.set_defaults(func=cmd_result)

    p = sub.add_parser("task-from-template", help="从流转模板发起工单")
    _add_data_dir_arg(p)
    p.add_argument("template", help="模板 ID（single-step / two-step-review / patrol-check）")
    p.add_argument("--intent", required=True, help="任务意图（做什么）")
    p.add_argument("--from", dest="from_agent", required=True, help="发起人 agent ID")
    p.add_argument("--task-id", dest="task_id", default="", help="自定义任务 ID（可选）")
    p.set_defaults(func=cmd_task_from_template)

    p = sub.add_parser("dlq", help="查看死信队列（push 终局失败 / 环路拦截）")
    _add_data_dir_arg(p)
    p.add_argument("--limit", type=int, default=20, help="显示最近 N 条（默认 20）")
    p.set_defaults(func=cmd_dlq)

    p = sub.add_parser("test-connection", help="E1 三段式测试连接（probe/发现预览/试发等ack）")
    _add_data_dir_arg(p)
    p.add_argument("instance", help="Agent 实例 ID（config.json agent_instances 键）")
    p.add_argument("--role", default="", help="试发目标角色（默认自动选择）")
    p.add_argument("--timeout", type=int, default=90, help="试发等 ack 超时秒数（默认 90）")
    p.add_argument("--no-load", dest="no_load", action="store_true", help="不自动上架发现的角色")
    p.set_defaults(func=cmd_test_connection)

    p = sub.add_parser("tokens", help="E3 token 台账：今日消耗视图 / 工单下钻")
    _add_data_dir_arg(p)
    p.add_argument("--task", default="", help="单工单下钻（尖峰归因）")
    p.add_argument("--limit", type=int, default=50, help="下钻条数（默认 50）")
    p.set_defaults(func=cmd_tokens)

    p = sub.add_parser("demo", help="零依赖演示：一条工单完整流转（建单→派工→执行→回执→验收→归档）")
    _add_data_dir_arg(p)
    p.add_argument("--intent", default="", help="演示工单意图（默认内置）")
    p.add_argument("--clean", action="store_true", help="一键清除演示数据（<store>/demo/）")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("stations", help="Wave 4 工位注册表（list / migrate）")
    _add_data_dir_arg(p)
    sub2 = p.add_subparsers(dest="action")
    pl = sub2.add_parser("list", help="查看工位注册表")
    _add_data_dir_arg(pl)
    pl.add_argument("--derived", action="store_true", help="显示将从 role-types 派生的表（未写盘）")
    pm = sub2.add_parser("migrate", help="从 role-types + org_defaults 迁移生成（幂等）")
    _add_data_dir_arg(pm)
    pm.add_argument("--force", action="store_true", help="覆盖已存在的工位定义")
    p.set_defaults(func=cmd_stations, action="list")

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
