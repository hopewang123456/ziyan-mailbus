#!/bin/bash
set -e
PORT="${MAILBUS_API_PORT:-9814}"
curl -sf "http://127.0.0.1:${PORT}/api/agents" -o /tmp/agents.json
python3 <<'PY'
import json
d = json.load(open("/tmp/agents.json"))
for k in ("lingxiao", "lingjian", "dali"):
    a = d.get("agents", {}).get(k, {})
    print(k, "has_desktop=", a.get("has_desktop"), "launch_modes=", a.get("launch_modes"))
PY
