#!/bin/bash
set -euo pipefail
docker exec docker-agents-openclaw-1 python3 <<'PY'
import json
for name in ("xiaoqi", "yige"):
    p = f"/workspace/data/.openclaw-{name}/openclaw.json"
    with open(p) as f:
        cfg = json.load(f)
    ids = [a["id"] for a in cfg.get("agents", {}).get("list", [])]
    print(f"{name} port={cfg['gateway']['port']} agents={ids}")
PY

echo "--- Hermes identity ---"
docker exec docker-agents-hermes-1 hermes chat -Q -q "你是谁？用一句话回答" --profile lingzhao 2>&1 | tail -6
