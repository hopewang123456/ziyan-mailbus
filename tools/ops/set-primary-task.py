#!/usr/bin/env python3
"""更新 iteration-state — 优先 Docker 容器写入，避免 WSL 权限/sudo 阻塞。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.privilege import write_via_mailbus_container, chown_store_path

DATA = os.environ.get("MAILBUS_DATA", "store")
task_id = sys.argv[1] if len(sys.argv) > 1 else "mailbus-scheduler-validation-20260616"
path = os.path.join(DATA, "iterations", "iteration-state.json")
host_path = os.path.abspath(path)

st = json.load(open(path, encoding="utf-8")) if os.path.isfile(path) else {}
st["primary_task_id"] = task_id
st["round1"] = {"phase": "execution", "status": "running"}
st["round2_unlocked"] = False
st["round3_unlocked"] = False
body = json.dumps(st, ensure_ascii=False, indent=2)

try:
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"primary_task_id -> {task_id}")
except PermissionError:
    if write_via_mailbus_container(host_path, body):
        print(f"primary_task_id -> {task_id} (via docker)")
    elif chown_store_path(host_path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        print(f"primary_task_id -> {task_id} (via sudo chown)")
    else:
        print("ERROR: 无法写入 iteration-state（配置 .env.secrets 中 SUDO_PASSWORD 或确保 mailbus 容器运行）", file=sys.stderr)
        sys.exit(1)
