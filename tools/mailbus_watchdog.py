#!/usr/bin/env python3
"""mailbus 外部看门狗（L2）— 独立进程守护 `python -m bus serve`（纯 Python，跨平台）。

职责：包住 serve 子进程，轮询 GET /api/health；连续失败 → 杀掉子进程 → 重启。
可抵抗「进程整体僵死」场景（此时 L1 进程内看门狗线程也可能无法自尽）。

用法:
  python tools/mailbus_watchdog.py --data-dir ./store [--host 0.0.0.0] [--port 9814] [--token ...]

环境变量:
  MAILBUS_WATCHDOG_INTERVAL   探测间隔秒（默认 10）
  MAILBUS_WATCHDOG_THRESHOLD  连续失败阈值（默认 3）
  MAILBUS_WATCHDOG_MAX_BACKOFF  重启退避上限秒（默认 60）

与 L1 的关系：
  - L1 在 serve 进程内，检测到假死先 dump 线程栈再自尽（退出码 70）。
  - L2 看到子进程异常退出（含 70），或健康检查连续失败，负责 kill + 重启。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lib.application.ops.watchdog import probe_health  # noqa: E402


def _build_cmd(args: argparse.Namespace) -> list[str]:
    cmd = [sys.executable, "-m", "bus", "serve"]
    if getattr(args, "data_dir", ""):
        cmd += ["--data-dir", args.data_dir]
    if getattr(args, "host", ""):
        cmd += ["--host", args.host]
    if getattr(args, "port", None):
        cmd += ["--port", str(args.port)]
    if getattr(args, "token", ""):
        cmd += ["--token", args.token]
    return cmd


def _terminate(proc: subprocess.Popen, timeout: float = 5.0) -> None:
    """跨平台终止子进程：先 terminate，超时后 kill。"""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="mailbus 外部看门狗（L2）")
    ap.add_argument("--data-dir", default="./store", help="store 数据目录")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--token", default="")
    args = ap.parse_args()

    from lib.infra.constants import DEFAULT_API_PORT
    port = args.port or DEFAULT_API_PORT

    try:
        interval = float(os.environ.get("MAILBUS_WATCHDOG_INTERVAL") or 10)
        threshold = int(os.environ.get("MAILBUS_WATCHDOG_THRESHOLD") or 3)
        max_backoff = float(os.environ.get("MAILBUS_WATCHDOG_MAX_BACKOFF") or 60)
    except ValueError:
        interval, threshold, max_backoff = 10.0, 3, 60.0

    cmd = _build_cmd(args)
    proc = subprocess.Popen(cmd, cwd=ROOT)
    print(f"[watchdog] 启动 serve: {' '.join(cmd)} (pid={proc.pid})")

    consecutive_fail = 0
    restarts = 0

    try:
        while True:
            time.sleep(interval)

            # 子进程已退出 → 直接重启（含 L1 自尽退出码 70）
            if proc.poll() is not None:
                code = proc.returncode
                print(f"[watchdog] serve 退出 (code={code})，重启中…")
                restarts += 1
                backoff = min(max_backoff, 2 ** (restarts - 1))
                time.sleep(backoff)
                proc = subprocess.Popen(cmd, cwd=ROOT)
                consecutive_fail = 0
                print(f"[watchdog] 已重启 serve (pid={proc.pid}, backoff={backoff:.0f}s)")
                continue

            # 健康检查
            if probe_health(port):
                consecutive_fail = 0
                continue

            consecutive_fail += 1
            print(f"[watchdog] 健康检查失败 {consecutive_fail}/{threshold}")
            if consecutive_fail >= threshold:
                print(f"[watchdog] 连续 {threshold} 次失败，终止并重启 serve…")
                _terminate(proc)
                restarts += 1
                backoff = min(max_backoff, 2 ** (restarts - 1))
                time.sleep(backoff)
                proc = subprocess.Popen(cmd, cwd=ROOT)
                consecutive_fail = 0
                print(f"[watchdog] 已重启 serve (pid={proc.pid})")
    except KeyboardInterrupt:
        print("\n[watchdog] 收到中断，清理子进程…")
        _terminate(proc)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
