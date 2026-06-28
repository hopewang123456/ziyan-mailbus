#!/bin/bash
for port in "${MAILBUS_API_PORT:-9814}" 9814; do
  echo "=== port $port ==="
  curl -sf "http://127.0.0.1:${port}/api/agents" -o "/tmp/agents-${port}.json" 2>/dev/null && \
    python3 -c "import json;d=json.load(open('/tmp/agents-${port}.json'));a=d.get('agents',{}).get('lingxiao',{});print('lingxiao has_desktop=',a.get('has_desktop'),'modes=',a.get('launch_modes'))" || \
    echo "NOT REACHABLE"
done
