#!/usr/bin/env python3
"""Device Bridge 模拟 Agent：盯 inbox，对 device:* 消息写 replies/{agent}.json。

用法（另开一个终端，先于 curl 启动）::

    python tools/device_bridge_mock_agent.py --agent test --data-dir ./store

然后在本机::

    curl.exe ... /api/device/chat ...

模拟器会在 delay 秒后写出回复；若 default_wait_ms 足够大，curl 会直接拿到 status=ok。
驾驶舱里把设备的 agent_id 绑到 ``test``（不要绑真人设）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _inbox_messages(inbox_path: Path) -> list[dict]:
    raw = _read_json(inbox_path, {})
    if isinstance(raw, list):
        return [m for m in raw if isinstance(m, dict)]
    if isinstance(raw, dict):
        return [m for m in (raw.get("messages") or []) if isinstance(m, dict)]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="模拟绑定 Agent 回复 Device Bridge 消息")
    ap.add_argument("--agent", default="test", help="绑定的 agent_id（默认 test）")
    ap.add_argument("--data-dir", default="./store", help="mailbus data_dir")
    ap.add_argument("--delay", type=float, default=1.5, help="看到消息后延迟多少秒再回复（模拟思考）")
    ap.add_argument("--prefix", default="[mock]", help="回复前缀")
    ap.add_argument("--once", action="store_true", help="只处理一条就退出")
    args = ap.parse_args()

    data_dir = Path(args.data_dir).resolve()
    inbox_path = data_dir / "inbox" / args.agent / "inbox.json"
    reply_path = data_dir / "replies" / f"{args.agent}.json"
    seen: set[str] = set()

    # 启动时把已有消息标成已见，避免把历史 ping 全回一遍
    for m in _inbox_messages(inbox_path):
        mid = str(m.get("id") or "")
        if mid:
            seen.add(mid)

    print(f"[mock-agent] watching agent={args.agent}")
    print(f"[mock-agent] inbox={inbox_path}")
    print(f"[mock-agent] replies={reply_path}")
    print(f"[mock-agent] delay={args.delay}s  (Ctrl+C 退出)")

    try:
        while True:
            for m in _inbox_messages(inbox_path):
                mid = str(m.get("id") or "")
                from_ = str(m.get("from") or "")
                if not mid or mid in seen:
                    continue
                if not from_.startswith("device:"):
                    continue
                seen.add(mid)
                text = str(m.get("content") or "").strip()
                print(f"[mock-agent] got {mid} from={from_} text={text[:80]!r}")
                time.sleep(max(0.0, args.delay))
                reply = f"{args.prefix} 收到：{text or '(空)'}"
                _write_json(reply_path, {"reply": reply, "msg_ids": [mid]})
                print(f"[mock-agent] wrote reply -> {reply_path.name}: {reply!r}")
                if args.once:
                    return 0
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\n[mock-agent] stopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
