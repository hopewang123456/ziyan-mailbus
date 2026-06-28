#!/usr/bin/env python3
"""CLI：POST Envelope 创建 task（供 shell 脚本调用）。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.environ.get("MAILBUS_API", "http://127.0.0.1:9814"))
    ap.add_argument("--file", help="Envelope JSON 文件")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--intent", required=True)
    ap.add_argument("--task-type", default="feature")
    ap.add_argument("--tier", default="M", choices=["S", "M", "L"])
    ap.add_argument("--mode", default="explicit", choices=["explicit", "auto"])
    ap.add_argument(
        "--planned-chain",
        help="role_type 逗号分隔，如 8,5,12",
    )
    args = ap.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            body = json.load(f)
    else:
        if args.mode == "explicit" and not args.planned_chain:
            print("explicit mode 需要 --planned-chain 或 --file", file=sys.stderr)
            return 2
        planned = []
        if args.planned_chain:
            for x in args.planned_chain.split(","):
                planned.append({"role_type": int(x.strip())})
        body = {
            "protocol_version": "mailbus-a2a/1",
            "task_id": args.task_id,
            "intent": args.intent,
            "initiator": "human",
            "mode": args.mode,
            "tier": args.tier,
            "task_type": args.task_type,
        }
        if planned:
            body["planned_chain"] = planned

    req = urllib.request.Request(
        f"{args.api.rstrip('/')}/api/tasks/create",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(err, file=sys.stderr)
        return e.code


if __name__ == "__main__":
    raise SystemExit(main())
