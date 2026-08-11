#!/usr/bin/env python3
"""Mailbus 全量诊断 — 等同 mailbus doctor 的结构化输出。"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.infra.env_bootstrap import load_mailbus_env
from lib.adapters.ops.doctor_checks import run_doctor_checks

load_mailbus_env()
report = run_doctor_checks()

print(f"platform={report.get('platform')}  ok={report.get('ok')}")
print(f"issues={report.get('issues')}  warnings={report.get('warnings')}")
print()

for item in report.get("items") or []:
    flag = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}.get(item["level"], "?")
    cat = item.get("category", "")
    msg = item.get("message", "")
    detail = item.get("detail", "")
    print(f"  {flag:4s} [{cat:12s}] {msg}")
    if detail and item.get("level") != "ok":
        print(f"       {detail}")
