#!/usr/bin/env python3
"""源码/Store 完整性 — 检查关键文件、transport、skills 目录。"""
import json, os, sys, urllib.request

MAIL_API = os.environ.get("MAILBUS_URL", "http://127.0.0.1:9814")

# 走 doctor API 拿到完整性部分
def api_get(path):
    try:
        req = urllib.request.Request(f"{MAIL_API}{path}", headers={"User-Agent": "clinic/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

doctor = api_get("/api/doctor")
integrity = [i for i in (doctor.get("items") or []) if i.get("category") == "integrity"]
manifest = [i for i in (doctor.get("items") or []) if i.get("category") == "manifest"]
paths = [i for i in (doctor.get("items") or []) if i.get("category") == "paths"]

print("=== 关键路径 ===")
for i in paths:
    print(f"  [{'OK' if i['level'] == 'ok' else i['level'].upper()}] {i['message']}: {i.get('detail', '')}")

print("\n=== 完整性检查 ===")
for i in integrity:
    print(f"  [{'OK' if i['level'] == 'ok' else i['level'].upper()}] {i['message']}: {i.get('detail', '')}")

print("\n=== Manifest 挂载 ===")
for i in manifest:
    flag = i["level"].upper()
    if flag == "WARN" and "optional" in i.get("message", ""):
        flag = "--"
    print(f"  [{flag}] {i['message']}: {i.get('detail', '')}")

fail_count = sum(1 for i in integrity + manifest + paths if i["level"] == "fail")
print(f"\nIntegrity: {'PASS' if fail_count == 0 else f'{fail_count} FAILURES'}")
