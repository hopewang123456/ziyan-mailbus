import json
from pathlib import Path

for port in (9812, 9814):
    p = Path(__file__).resolve().parent / f"tmp-agents-{port}.json"
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/agents", timeout=5) as r:
            d = json.loads(r.read().decode())
    except Exception as e:
        print(f"=== {port} === FAIL {e}")
        continue
    print(f"=== {port} ===")
    for k in ("lingxiao", "lingjian", "dali"):
        a = d.get("agents", {}).get(k, {})
        print(k, "has_desktop=", a.get("has_desktop"), "modes=", a.get("launch_modes"))
