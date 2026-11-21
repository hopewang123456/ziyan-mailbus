#!/usr/bin/env python3
"""Mailbus 员工心跳守护。

每个员工使用自己的 token 调用 SELF 接口：
    POST /api/identity/staff/{employee_id}/heartbeat
不依赖 Docker，也不依赖 agent 运行时；容器内跑 sidecar，宿主也可直接执行。

环境变量：
    MAILBUS_API_URL          API 基地址（默认 http://127.0.0.1:9814）
    MAILBUS_TOKENS_FILE      token 文件路径（默认 ./hermes-agent-tokens.json）
    HEARTBEAT_INTERVAL_SEC   上报间隔（默认 60，须小于服务端 180s 超时）
    HEARTBEAT_TIMEOUT_SEC    单次请求超时（默认 10）
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

_running = True


def _log(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def _stop(signum: int, _frame: object) -> None:
    global _running
    _running = False
    _log(f"收到信号 {signum}，准备退出")


def _load_agents(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        agents = json.load(fh)
    if not isinstance(agents, list):
        raise ValueError("token 文件格式应为数组")
    return [
        a for a in agents if a.get("employee_id") and a.get("token")
    ]


def _beat(api: str, agent: dict, timeout: float) -> int:
    request = urllib.request.Request(
        f"{api}/api/identity/staff/{agent['employee_id']}/heartbeat",
        method="POST",
        headers={"Authorization": f"Bearer {agent['token']}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()
        return response.status


def _describe(agent: dict) -> str:
    return agent.get("slug") or agent["employee_id"]


def main() -> int:
    api = os.environ.get("MAILBUS_API_URL", "http://127.0.0.1:9814").rstrip("/")
    tokens_file = Path(
        os.environ.get("MAILBUS_TOKENS_FILE", "hermes-agent-tokens.json")
    ).resolve()
    interval = float(os.environ.get("HEARTBEAT_INTERVAL_SEC", "60"))
    timeout = float(os.environ.get("HEARTBEAT_TIMEOUT_SEC", "10"))

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    _log(f"启动：api={api} tokens={tokens_file} interval={interval:g}s")

    healthy: dict[str, bool] = {}
    while _running:
        tick_started = time.monotonic()
        try:
            agents = _load_agents(tokens_file)
        except Exception as exc:  # 文件缺失/损坏不应终止守护进程
            _log(f"读取 token 文件失败：{exc}")
            agents = []

        for agent in agents:
            if not _running:
                break
            name = _describe(agent)
            try:
                status = _beat(api, agent, timeout)
            except urllib.error.HTTPError as exc:
                if healthy.get(name) is not False:
                    _log(f"{name} 心跳失败：HTTP {exc.code}")
                healthy[name] = False
            except Exception as exc:
                if healthy.get(name) is not False:
                    _log(f"{name} 心跳失败：{type(exc).__name__} {exc}")
                healthy[name] = False
            else:
                if healthy.get(name) is not True:
                    _log(f"{name} 心跳成功：HTTP {status}")
                healthy[name] = True

        elapsed = time.monotonic() - tick_started
        sleep_for = max(0.0, interval - elapsed)
        end = time.monotonic() + sleep_for
        while _running and time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))

    _log("已退出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
