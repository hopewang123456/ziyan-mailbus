#!/usr/bin/env python3
"""M1 W3 宿主哨兵（sentinel）— 在 mailbus 进程之外守望 mailbus。

2026-09 停摆事故的根治层：serve 容器/scheduler 全死时，cron.log 停更、
patrol 停产——只有**宿主侧独立进程**能发现并外呼。本脚本即那个进程：

  acceptance 对账（六项，只读 store 文件系统 + health ping）
    → 新增 warn 立即外呼 critical（满足「停摆 ≤10 分钟触达」）
    → 持续 warn 每 24h 提醒一次（不轰炸）
    → 恢复（warn 清零）外呼一次
    → 每天 12:00 后首次运行推当日 digest 摘要

安装（Windows 宿主，每 10 分钟）：
  schtasks /create /tn mailbus-sentinel ^
    /tr "\"D:\\Programs\\Python\\Python314\\pythonw.exe\" \"<repo>\\tools\\mailbus_sentinel.py\"" ^
    /sc minute /mo 10 /f
卸载：schtasks /delete /tn mailbus-sentinel /f

Linux（systemd timer 版，开源用户）：
  [Timer] OnCalendar=*:0/10  +  [Service] ExecStart=<python> <repo>/tools/mailbus_sentinel.py
  或 crontab: */10 * * * * <python> <repo>/tools/mailbus_sentinel.py >> /var/log/mailbus-sentinel.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib.adapters.ops.acceptance import acceptance_status, format_acceptance_text  # noqa: E402
from lib.adapters.ops.notifier import send_notification  # noqa: E402

STATE_FILE = os.path.join("notify", "sentinel-state.json")
RECOVERY_COOLDOWN_H = 1.0  # 恢复通知的最小间隔，防抖


def _default_data_dir() -> str:
    return os.path.join(_ROOT, "store")


def _load_state(data_dir: str) -> dict:
    path = os.path.join(data_dir, STATE_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_state(data_dir: str, state: dict) -> None:
    path = os.path.join(data_dir, STATE_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)


def _hours_since(iso: str, now) -> float:
    if not iso:
        return 1e9
    try:
        from datetime import datetime

        t = datetime.fromisoformat(iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=now.tzinfo)
        return (now - t).total_seconds() / 3600
    except ValueError:
        return 1e9


def run_sentinel(data_dir: str, *, api_base: str = "http://127.0.0.1:9814",
                 remind_hours: float = 24.0) -> dict:
    """跑一轮对账 + 节流外呼；返回本轮动作摘要（哨兵自身日志/测试用）。"""
    from lib.infra.clock import now_dt

    now = now_dt()
    report = acceptance_status(data_dir, api_base=api_base)
    warn_items = {k: v["detail"] for k, v in report["items"].items() if v["status"] == "warn"}
    state = _load_state(data_dir)
    prev_warns = set(state.get("warn_keys") or [])
    cur_warns = set(warn_items)
    actions = []

    if cur_warns - prev_warns:
        # 新增 warn：立即外呼（停摆发现的主路径）
        body = "\n".join(f"✗ {k}: {d}" for k, d in sorted(warn_items.items()))
        send_notification(data_dir, "mailbus 哨兵：发现异常", body, level="critical")
        actions.append("alert:new_warn")
        state["last_alert_at"] = now.isoformat()
    elif cur_warns and _hours_since(state.get("last_alert_at") or "", now) >= remind_hours:
        body = "\n".join(f"✗ {k}: {d}" for k, d in sorted(warn_items.items()))
        send_notification(data_dir, f"mailbus 哨兵：仍有 {len(cur_warns)} 项异常（每日提醒）", body, level="warn")
        actions.append("alert:remind")
        state["last_alert_at"] = now.isoformat()
    elif prev_warns and not cur_warns and _hours_since(state.get("last_alert_at") or "", now) >= 0:
        send_notification(data_dir, "mailbus 哨兵：异常已恢复", "此前告警项已全部转绿。", level="warn")
        actions.append("alert:recovered")

    # 每日 digest：12:00 后首次运行
    today = now.strftime("%Y-%m-%d")
    if now.hour >= 12 and state.get("last_digest_day") != today:
        send_notification(
            data_dir, f"mailbus 哨兵日报 {today}",
            format_acceptance_text(report).strip(), level="digest",
        )
        actions.append("digest")
        state["last_digest_day"] = today

    state["warn_keys"] = sorted(cur_warns)
    state["last_run_at"] = now.isoformat()
    _save_state(data_dir, state)
    return {"actions": actions, "warns": sorted(cur_warns), "ok": report["ok"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mailbus-sentinel", description="mailbus 宿主哨兵（M1 W3）")
    ap.add_argument("--data-dir", default="", help="store 目录（默认 <repo>/store）")
    ap.add_argument("--api-base", default="http://127.0.0.1:9814")
    ap.add_argument("--remind-hours", type=float, default=24.0, help="持续异常的提醒间隔（默认 24h）")
    args = ap.parse_args(argv)

    data_dir = args.data_dir or _default_data_dir()
    summary = run_sentinel(data_dir, api_base=args.api_base, remind_hours=args.remind_hours)
    # 计划任务常用 pythonw（无控制台，stdout 为 None）：print 需容错
    if summary["actions"]:
        from lib.infra.clock import now_iso

        try:
            print(f"[{now_iso()}] sentinel actions={summary['actions']} warns={summary['warns']}")
        except (OSError, ValueError):
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
