#!/usr/bin/env python3
"""V3 夜间监控：scan + 卡步重推 + 终态报告。

用法:
  python3 tools/monitor-v3-until-done.py
  python3 tools/monitor-v3-until-done.py --loop 120 --interval 180
  python3 tools/monitor-v3-until-done.py --report-only
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

TASK_ID = "game-stellar-v3-20260617"
TZ = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


def _load_task(data_dir: str):
    from lib.task_fsm import ensure_fsm, fsm_summary, get_active_step
    from lib.tracker import TaskTracker

    t = TaskTracker(data_dir).get(TASK_ID)
    if not t:
        return None, None, None
    ensure_fsm(t)
    return t, fsm_summary(t), get_active_step(t)


def _step_result_path(data_dir: str, step: dict) -> str:
    ref = (step or {}).get("result_ref") or f"msg-results/{TASK_ID}/step-s5.json"
    if ref.startswith("msg-results/"):
        return os.path.join(data_dir, ref)
    return os.path.join(data_dir, "msg-results", TASK_ID, f"step-{step.get('step_id', 's5')}.json")


def _terminal(fsm: dict) -> bool:
    return fsm.get("fsm_state") in ("succeeded", "cancelled", "failed", "blocked")


def _run_scan(data_dir: str, quiet: bool = True) -> int:
    from lib.commands import load_config, run_scan_once
    cfg = load_config(os.path.join(data_dir, "config.json"))
    return run_scan_once(data_dir, cfg, quiet=quiet)


def _maybe_repush(data_dir: str, active: dict, stale_min: float) -> bool:
    """卡步超过 stale_min 且 inbox 无 processing 时重推 Step5。"""
    if not active or active.get("to_person") != "lingxiao":
        return False
    if active.get("step_id") != "s5":
        return False
    started = active.get("started_at") or ""
    if not started:
        return False
    try:
        from lib.tracker import _parse_iso_dt
        age = (datetime.now(TZ) - _parse_iso_dt(started).astimezone(TZ)).total_seconds() / 60
    except Exception:
        age = 999
    if age < stale_min:
        return False
    script = os.path.join(MAIL, "tools", "repush-v3-step5.py")
    if not os.path.isfile(script):
        return False
    subprocess.run([sys.executable, script], cwd=MAIL, timeout=300)
    return True


def generate_report(data_dir: str, *, note: str = "") -> str:
    from lib.utils import json_read, resolve_paths

    t, fsm, active = _load_task(data_dir)
    lines = [
        f"# V3 Pipeline 运行报告 — {TASK_ID}",
        "",
        f"> 生成时间: {_now()}",
        "",
    ]
    if note:
        lines.extend([f"> {note}", ""])

    if not t:
        lines.append("**错误**: 任务未找到")
        out = _write_report(data_dir, lines)
        return out

    lines.extend([
        "## FSM 摘要",
        "",
        f"- **状态**: `{fsm.get('fsm_state')}`",
        f"- **优先级**: {fsm.get('priority')}",
        f"- **活跃步骤**: `{fsm.get('active_step_id')}` → {active.get('to_person') if active else '?'} ({active.get('to_role') if active else '?'})",
        "",
        "## 步骤进度",
        "",
        "| Step | ID | 角色 | Agent | FSM | 结果文件 |",
        "|------|-----|------|-------|-----|----------|",
    ])

    for s in fsm.get("steps") or []:
        rp = s.get("result_ref", "")
        full = os.path.join(data_dir, rp.replace("/mailbus/store/", "")) if rp else ""
        exists = "✅" if full and os.path.isfile(full) else "—"
        lines.append(
            f"| {s.get('step')} | {s.get('step_id')} | {s.get('to_role')} | {s.get('to_person')} "
            f"| {s.get('fsm_state')} | {exists} |"
        )

    if active:
        rp = _step_result_path(data_dir, active)
        lines.extend([
            "",
            "## 当前步骤",
            "",
            f"- 等待: **{active.get('to_person')}** 写入 `{rp}`",
            f"- 结果文件存在: {'是' if os.path.isfile(rp) else '否'}",
        ])

    # token 快照
    try:
        import urllib.request
        from lib.constants import DEFAULT_API_BASE
        with urllib.request.urlopen(f"{DEFAULT_API_BASE}/api/status", timeout=5) as r:
            st = json.loads(r.read())
        sched = st.get("scheduler") or {}
        ta = sched.get("token_activity") or {}
        lines.extend([
            "",
            "## Mailbus 快照",
            "",
            f"- scan 间隔: {sched.get('scan_interval_effective')}s",
            f"- pending 消息: {ta.get('pending_messages', '?')}",
            f"- running 任务: {ta.get('running_tasks', '?')}",
        ])
    except Exception:
        pass

    lines.extend([
        "",
        "## 结论",
        "",
    ])
    state = fsm.get("fsm_state")
    if state == "succeeded":
        lines.append("✅ **V3 全链完成**")
    elif state == "executing":
        lines.append(f"⏳ **进行中** — 等待 Step {active.get('step') if active else '?'} ({active.get('to_person') if active else '?'})")
    elif state == "paused":
        lines.append("⏸ **已暂停** — 需 `tools/resume-v3-task.py`")
    else:
        lines.append(f"状态: `{state}`")

    lines.extend([
        "",
        "---",
        "*报告由 tools/monitor-v3-until-done.py 自动生成*",
    ])
    return _write_report(data_dir, lines)


def _write_report(data_dir: str, lines: list) -> str:
    reports_dir = os.path.join(data_dir, "reports", "v3-runs")
    os.makedirs(reports_dir, exist_ok=True)
    ts = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
    path = os.path.join(reports_dir, f"v3-run-{ts}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    latest = os.path.join(reports_dir, "LATEST.md")
    with open(latest, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"report: {path}")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(MAIL, "store"))
    ap.add_argument("--loop", type=int, default=0, help="0=单次检查后退出；>0 循环次数")
    ap.add_argument("--interval", type=int, default=180, help="循环间隔秒")
    ap.add_argument("--stale-min", type=float, default=20, help="卡步重推阈值分钟")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    if args.report_only:
        generate_report(args.data_dir)
        return 0

    loops = max(1, args.loop) if args.loop else 1
    for i in range(loops):
        t, fsm, active = _load_task(args.data_dir)
        print(f"[{_now()}] V3 monitor cycle {i + 1}/{loops} fsm={fsm.get('fsm_state') if fsm else '?'}")

        if fsm and _terminal(fsm):
            generate_report(args.data_dir, note="终态达成")
            return 0

        if active and not os.path.isfile(_step_result_path(args.data_dir, active)):
            _maybe_repush(args.data_dir, active, args.stale_min)

        _run_scan(args.data_dir, quiet=True)

        t2, fsm2, active2 = _load_task(args.data_dir)
        if fsm2 and fsm2.get("fsm_state") == "succeeded":
            generate_report(args.data_dir, note="监控期间全链完成")
            return 0

        if i == 0 or (i + 1) == loops:
            generate_report(args.data_dir, note=f"周期 {i + 1}/{loops}")

        if i < loops - 1:
            time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
