#!/usr/bin/env python3
"""n8n 发布 Workflow — 确保 mailbus-multi-publish workflow 已导入并激活（WSL Docker）。"""
import json, os, subprocess, sys, urllib.request

N8N_API = os.environ.get("N8N_API_URL", "http://127.0.0.1:5678/rest")

def main():
    try:
        req = urllib.request.Request(
            f"{N8N_API}/workflows?active=true",
            headers={"User-Agent": "clinic/1.0", "X-N8N-API-KEY": os.environ.get("N8N_API_KEY", "")})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"N8N API unreachable: {e}")
        print("  n8n 可能未启动，请通过 docker-compose.n8n.yml 启动")
        return 2

    wfs = data.get("data") or []
    mailbus_wfs = [w for w in wfs if "mailbus" in w.get("name", "").lower()]
    print(f"n8n workflows: {len(wfs)} total, {len(mailbus_wfs)} mailbus-related")

    if mailbus_wfs:
        for w in mailbus_wfs:
            active = w.get("active", False)
            vid = w.get("versionId", "?")
            print(f"  [{'ACTIVE' if active else 'INACTIVE'}] {w.get('name', '?')}  v={vid}")
        return 0
    else:
        print("WARN: no mailbus workflows found, import via n8n UI")
        return 1

if __name__ == "__main__":
    exit(main())
