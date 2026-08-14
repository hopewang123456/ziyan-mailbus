#!/usr/bin/env python3
"""最短 agent 真实落盘探针 — 经 mailbus 推送 + scan，轮询磁盘探针文件。

不创建 pipeline tracker，不跑 12 步链。仅验证：agent CLI 能否写入共享 store。

用法（mailbus 容器内）:
  python3 tools/smoke-agent-disk-write.py --agent agent-a
  python3 tools/smoke-agent-disk-write.py --agent agent-a --timeout 600

退出码: 0=落盘成功, 1=超时/内容不符, 2=推送失败
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TZ_CN = timezone(timedelta(hours=8))
MAIL_ROOT = os.environ.get("MAILBUS_ROOT", "/mailbus")


def log(msg: str) -> None:
    print(f"[smoke-write] {msg}", flush=True)


def send_probe(api: str, agent: str, content: str) -> str:
    payload = {
        "to": agent,
        "from": "mailbus",
        "content": content,
        "type": "task",
        "priority": "urgent",
    }
    req = urllib.request.Request(
        f"{api}/api/send-msg",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data.get("msg_id", "?")


def trigger_scan(data_dir: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "bus", "scan", "--data-dir", data_dir],
        cwd=MAIL_ROOT,
        timeout=180,
        check=False,
    )


def validate_probe(path: str, agent: str, run_id: str) -> tuple[bool, str]:
    if not os.path.isfile(path):
        return False, "file missing"
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"invalid json: {exc}"
    if not data.get("probe"):
        return False, "probe flag missing"
    if data.get("agent") != agent:
        return False, f"agent mismatch: {data.get('agent')}"
    if data.get("run_id") != run_id:
        return False, f"run_id mismatch: {data.get('run_id')}"
    if not data.get("timestamp"):
        return False, "timestamp missing"
    return True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser(description="Agent 落盘最短探针")
    ap.add_argument("--agent", default="agent-a")
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "store"))
    from lib.infra.constants import DEFAULT_API_BASE
    ap.add_argument("--api", default=os.environ.get("MAILBUS_API", DEFAULT_API_BASE))
    ap.add_argument("--timeout", type=int, default=420, help="等待落盘秒数")
    ap.add_argument("--poll", type=int, default=15, help="轮询间隔秒")
    ap.add_argument("--no-scan", action="store_true", help="仅发送不 scan（调试）")
    args = ap.parse_args()

    run_id = datetime.now(TZ_CN).strftime("%Y%m%d-%H%M%S")
    probe_name = f"agent-write-{run_id}.json"
    probe_path = os.path.join(os.path.abspath(args.data_dir), "probes", probe_name)
    os.makedirs(os.path.dirname(probe_path), exist_ok=True)
    if os.path.isfile(probe_path):
        os.remove(probe_path)

    log(f"agent={args.agent} run_id={run_id}")
    log(f"expect file: {probe_path}")

    content = (
        f"【probe-{run_id}】Agent 落盘探针 — 仅写文件\n\n"
        f"覆盖写入（必须真实落盘）:\n{probe_path}\n\n"
        f"JSON 内容（仅替换 timestamp 为当前 ISO8601+08:00）:\n"
        f'{{"probe":true,"run_id":"{run_id}","agent":"{args.agent}","timestamp":"<ISO8601+08:00>"}}\n\n'
        f"禁止只写 ack 或 stdout 声称完成。无磁盘文件 = 失败。\n"
        f"路径: /mailbus/store/probes/\n"
    )

    try:
        msg_id = send_probe(args.api, args.agent, content)
        log(f"API send-msg ok msg_id={msg_id}")
    except (urllib.error.URLError, RuntimeError) as exc:
        log(f"FAIL send: {exc}")
        return 2

    if not args.no_scan:
        log("trigger bus scan...")
        trigger_scan(args.data_dir)

    deadline = time.time() + args.timeout
    round_n = 0
    while time.time() < deadline:
        round_n += 1
        ok, reason = validate_probe(probe_path, args.agent, run_id)
        if ok:
            log(f"PASS round={round_n} file validated")
            log(json.dumps(json.load(open(probe_path, encoding="utf-8")), ensure_ascii=False))
            return 0
        log(f"wait round={round_n} ({reason}) — rescan in {args.poll}s")
        time.sleep(args.poll)
        if not args.no_scan and round_n % 2 == 0:
            trigger_scan(args.data_dir)

    log(f"FAIL timeout {args.timeout}s — probe not on disk")
    replies = os.path.join(args.data_dir, "replies", f"{args.agent}.json")
    if os.path.isfile(replies):
        rep = json.load(open(replies, encoding="utf-8"))
        snippet = (rep.get("reply") or "")[:300]
        if snippet:
            log(f"replies snippet: {snippet!r}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
