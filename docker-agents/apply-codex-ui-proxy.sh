#!/usr/bin/env bash
# 热更新 codex-ui-proxy（WebSocket 转发）并重启 UI
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROJECT="${COMPOSE_PROJECT_NAME:-docker-agents}"
PROXY="$ROOT/codex-agent/codex-ui-proxy.mjs"

for name in codex-web codex-review; do
  ctr="${PROJECT}-${name}-1"
  echo "=== $ctr ==="
  docker cp "$PROXY" "${ctr}:/usr/local/share/codex/codex-ui-proxy.mjs"
  docker exec "$ctr" bash -lc '
    render-codex-config.sh
    rm -f /home/node/.codex/auth.json
    pkill -f codex-ui-proxy || true
    pkill -f codexapp || true
    pkill -f "codex app-server" || true
    sleep 2
    start-codex-ui.sh
  '
done

sleep 3
for p in 9240 9241; do
  curl -sf -o /dev/null -w ":$p=%{http_code} " "http://127.0.0.1:$p/" || echo ":$p=fail "
done
echo
python3 - <<'PY'
import socket
for port in (9240, 9241):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.settimeout(5)
    s.sendall(
        b"GET /codex-api/ws HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Upgrade: websocket\r\n"
        b"Connection: Upgrade\r\n"
        b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        b"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    data = s.recv(200).decode("utf-8", "replace")
    ok = "101 Switching Protocols" in data
    print(f"ws :{port}", "OK" if ok else data[:80])
    s.close()
PY
echo "=== done ==="
