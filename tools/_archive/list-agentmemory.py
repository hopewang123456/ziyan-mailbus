#!/usr/bin/env python3
import json, urllib.request
url = "http://127.0.0.1:3111/agentmemory/memories?limit=30"
with urllib.request.urlopen(url, timeout=10) as r:
    d = json.load(r)
print("total", d.get("total", len(d.get("memories", []))))
for m in d.get("memories", [])[:20]:
    aid = m.get("agentId", "-")
    concepts = m.get("concepts") or []
    content = (m.get("content") or "")[:100].replace("\n", " ")
    print(f"  agentId={aid} concepts={concepts[:4]} | {content}")
