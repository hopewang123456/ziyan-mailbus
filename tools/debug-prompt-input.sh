#!/bin/bash
docker exec docker-agents-lingxiao-1 bash -lc '
export CODEX_HOME=/home/node/.codex
cd /home/node/agent-workspace/lingxiao
echo "=== prompt-input from project dir ==="
codex debug prompt-input --cd /home/node/agent-workspace/lingxiao 2>&1 | head -80
echo "=== models ==="
codex debug models 2>&1 | head -20
'
