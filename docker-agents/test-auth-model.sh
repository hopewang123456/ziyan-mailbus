#!/bin/bash
docker exec docker-agents-lingxiao-1 bash -lc '
export CODEX_HOME=/home/node/.codex
echo "=== auth.json (redacted) ==="
python3 -c "import json; d=json.load(open(\"/home/node/.codex/auth.json\")); print({k:(v[:8]+\"...\" if isinstance(v,str) and len(v)>8 else v) for k,v in d.items()})" 2>/dev/null || cat /home/node/.codex/auth.json

echo "=== logout test ==="
codex logout 2>&1 || true
codex login status 2>&1 || true

echo "=== exec without re-login ==="
timeout 60 codex exec --json --ephemeral --skip-git-repo-check --cd /mailbus/store \
  -s workspace-write -c '"'"'approval_policy="never"'"'"' \
  -m deepseek-v4-flash "Reply OK" 2>&1 | tail -5

echo "=== gateway model big-pickle ==="
curl -sf -m 25 http://127.0.0.1:3000/v1/responses \
  -H "Content-Type: application/json" \
  -d '"'"'{"model":"big-pickle","input":"Say OK"}'"'"' 2>&1 | head -c 250; echo
'
