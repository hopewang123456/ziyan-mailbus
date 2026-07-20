#!/bin/bash
set -uo pipefail

WIN_HOST="$(grep -m1 '^nameserver' /etc/resolv.conf | awk '{print $2}')"
echo "=== WSL Windows host IP (resolv nameserver) ==="
echo "$WIN_HOST"

echo "=== ExtraHosts on mailbus container ==="
docker inspect docker-agents-mailbus-1 --format '{{json .HostConfig.ExtraHosts}}'

probe_url() {
  local label="$1"
  local url="$2"
  echo "--- $label: $url ---"
  if docker exec docker-agents-mailbus-1 python3 -c "
import urllib.request, sys
try:
    r = urllib.request.urlopen('${url}', timeout=10)
    print('OK', len(r.read()))
except Exception as exc:
    print('FAIL', exc)
    sys.exit(1)
"; then
    return 0
  fi
  return 1
}

echo "=== Probes from mailbus container ==="
probe_url "host.docker.internal" "http://host.docker.internal:11434/api/tags" || true
if [ -n "$WIN_HOST" ]; then
  probe_url "windows-host-ip" "http://${WIN_HOST}:11434/api/tags" || true
fi

echo "=== Health API ==="
curl -sf http://127.0.0.1:9814/api/internal-llm/health | python3 -m json.tool || echo "health failed"

echo "=== Dry-run API ==="
DRY=$(curl -s -X POST http://127.0.0.1:9814/api/internal-llm/dry-run \
  -H 'Content-Type: application/json' \
  -d '{"intent":"评估 Redis 缓存方案","task_type":"custom","tier":"M"}')
echo "$DRY" | python3 -m json.tool 2>/dev/null || echo "$DRY"
