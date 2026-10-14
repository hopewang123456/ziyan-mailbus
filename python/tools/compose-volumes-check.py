#!/usr/bin/env python3
"""Compose 挂载校验 — 检查 docker-compose v3 挂载与 override drift。"""
import json, os, sys, urllib.request

MAIL_API = os.environ.get("MAILBUS_URL", "http://127.0.0.1:9814")

def api_get(path):
    try:
        req = urllib.request.Request(f"{MAIL_API}{path}", headers={"User-Agent": "clinic/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

doctor = api_get("/api/doctor")
compose = [i for i in (doctor.get("items") or []) if i.get("category") == "compose"]
frameworks = [i for i in (doctor.get("items") or []) if i.get("category") == "frameworks"]
docker = [i for i in (doctor.get("items") or []) if i.get("category") == "docker"]

print("=== Docker ===")
for i in docker:
    print(f"  [{'OK' if i['level'] == 'ok' else i['level'].upper()}] {i['message']}: {i.get('detail', '')}")

print("\n=== Compose ===")
for i in compose:
    print(f"  [{'OK' if i['level'] == 'ok' else i['level'].upper()}] {i['message']}: {i.get('detail', '')}")

print("\n=== Frameworks ===")
for i in frameworks:
    msg = i.get("message", "")
    is_warn = i["level"] == "warn"
    flag = "OK" if i["level"] == "ok" else ("WARN" if is_warn else "FAIL")
    print(f"  [{flag}] {msg}")
    if i.get("detail"):
        print(f"       {i['detail']}")

# 检查 compose override 是否存在
status = api_get("/api/status")
agents = status.get("agent_statuses", {})
print(f"\n=== Agent 容器对账 ===")
for aid, info in sorted(agents.items()):
    atype = info.get("type", "?")
    msg_cnt = info.get("active_messages", 0)
    print(f"  {aid:12s}  type={atype:16s}  msgs={msg_cnt}  {'unread' if info.get('has_unread') else 'read'}")
