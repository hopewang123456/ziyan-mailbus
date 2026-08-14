"""mailbus 服务自愈 — 进程内看门狗 + faulthandler 现场抓取（纯 Python，跨平台）。

分层（按可靠性递增）：
- L0 faulthandler：服务启动时启用；看门狗触发 / 致命信号时 dump 全部线程栈，便于定位假死根因。
- L1 进程内看门狗线程：定时 GET /api/health，连续失败 → dump 线程栈 → os._exit(非零)，宁可自尽也不假死。
- L2 外部看门狗：见 tools/mailbus_watchdog.py，负责在进程整体僵死（L1 也无法自尽）时 kill + 重启。

配置（环境变量，部署层注入，跨平台一致）：
- MAILBUS_SELF_WATCHDOG=0     关闭 L1（默认 1）
- MAILBUS_WATCHDOG_INTERVAL   探测间隔秒（默认 10）
- MAILBUS_WATCHDOG_THRESHOLD  连续失败次数阈值（默认 3）
"""

from __future__ import annotations

import faulthandler
import json
import os
import threading
import urllib.request
from typing import Optional

HEALTH_PATH = "/api/health"
EXIT_STALL = 70  # 看门狗触发的非零退出码，供外部识别为异常退出


def enable_faulthandler(data_dir: str) -> None:
    """启用 faulthandler，把致命信号/看门狗触发时的线程栈写入 store/logs。"""
    try:
        log_dir = os.path.join(data_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        fh = open(os.path.join(log_dir, "faulthandler.log"), "a", encoding="utf-8", buffering=1)
        faulthandler.enable(file=fh, all_threads=True)
    except Exception:
        faulthandler.enable(all_threads=True)


def dump_threads(data_dir: str, reason: str = "") -> None:
    """立即 dump 所有线程栈到日志（看门狗自尽前调用）。"""
    try:
        log_dir = os.path.join(data_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "watchdog-stall.log")
        with open(path, "a", encoding="utf-8", buffering=1) as fh:
            fh.write(f"\n=== watchdog stall: {reason} ===\n")
            faulthandler.dump_traceback(file=fh, all_threads=True)
    except Exception:
        faulthandler.dump_traceback(all_threads=True)


def probe_health(port: int, *, host: str = "127.0.0.1", timeout: float = 3.0) -> bool:
    """GET /api/health，返回服务是否存活（HTTP 200 且 JSON status=ok）。"""
    url = f"http://{host}:{port}{HEALTH_PATH}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            body = resp.read(256)
            data = json.loads(body.decode("utf-8") or "{}")
            return data.get("status") == "ok"
    except Exception:
        return False


def _is_enabled() -> bool:
    return os.environ.get("MAILBUS_SELF_WATCHDOG", "1").lower() not in ("0", "false", "no", "off")


def start_self_watchdog(
    port: int,
    data_dir: str,
    *,
    interval: float = 10.0,
    threshold: int = 3,
) -> Optional[threading.Thread]:
    """启动 L1 进程内看门狗线程。返回线程，或 None（已禁用 / 参数非法）。

    探测固定走回环 127.0.0.1（而非 serve 的监听 host，如 0.0.0.0 不可作为连接目标）。
    """
    if not _is_enabled():
        return None
    try:
        interval = float(os.environ.get("MAILBUS_WATCHDOG_INTERVAL") or interval)
        threshold = int(os.environ.get("MAILBUS_WATCHDOG_THRESHOLD") or threshold)
    except ValueError:
        pass
    if interval <= 0 or threshold <= 0:
        return None

    def _run() -> None:
        import time

        fail = 0
        while True:
            time.sleep(interval)
            if probe_health(port):
                fail = 0
                continue
            fail += 1
            if fail >= threshold:
                dump_threads(data_dir, reason=f"health check failed {fail} times")
                os._exit(EXIT_STALL)

    t = threading.Thread(target=_run, name="mailbus-self-watchdog", daemon=True)
    t.start()
    return t
