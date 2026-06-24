#!/bin/bash
curl -sf http://127.0.0.1:9812/api/permission -o /tmp/perm.json
python3 <<'PY'
import json
d = json.load(open("/tmp/perm.json"))
p = d.get("permissions", {})
for k in ("lingxiao", "lingjian", "dali"):
    print(k, p.get(k))
PY
