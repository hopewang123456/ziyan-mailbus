#!/bin/bash
set -uo pipefail
WIN="$(grep -m1 '^nameserver' /etc/resolv.conf | awk '{print $2}')"
echo "WIN_HOST=$WIN"
for url in \
  "http://127.0.0.1:11434/api/tags" \
  "http://${WIN}:11434/api/tags" \
  "http://host.docker.internal:11434/api/tags"; do
  echo -n "$url -> "
  curl -sf --max-time 3 "$url" | head -c 80 && echo || echo FAIL
done
if command -v ollama >/dev/null 2>&1; then echo "WSL ollama: $(which ollama)"; else echo "WSL ollama: not installed"; fi
