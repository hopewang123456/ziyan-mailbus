import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:9814/api/agents", timeout=10) as r:
    d = json.loads(r.read().decode())
lx = d.get("agents", {}).get("lingxiao", {})
print("lingxiao keys:", sorted(lx.keys()))
print("lingxiao:", json.dumps(lx, ensure_ascii=False, indent=2)[:800])
