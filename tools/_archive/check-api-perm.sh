#!/bin/bash
PORT="${MAILBUS_API_PORT:-9814}"
curl -sf "http://127.0.0.1:${PORT}/api/permission" -o /tmp/perm.json
python3 <<'PY'
import json
d = json.load(open("/tmp/perm.json"))
p = d.get("permissions", {})
for k in ("lingxiao", "lingjian", "dali"):
    print(k, p.get(k))
PY
