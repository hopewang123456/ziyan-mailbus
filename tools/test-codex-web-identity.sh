#!/bin/bash
# 灵鉴 Web UI 人设冒烟 — 需在容器内 codexapp 已启动时运行
set -euo pipefail
AGENT="${1:-lingjian}"
case "$AGENT" in
  lingxiao) CONTAINER=docker-agents-lingxiao-1; CWD=/home/node/agent-workspace/lingxiao; NEED=灵霄 ;;
  lingjian) CONTAINER=docker-agents-lingjian-1; CWD=/home/node/agent-workspace/lingjian; NEED=灵鉴 ;;
  *) echo "unknown agent: $AGENT"; exit 1 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker cp "${SCRIPT_DIR}/_run_identity_test.py" "${CONTAINER}:/tmp/_run_identity_test.py"
docker exec "$CONTAINER" python3 /tmp/_run_identity_test.py "$CWD" "$NEED"
