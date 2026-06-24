#!/bin/bash
# 通过 app-server JSON-RPC 测试人设是否生效
set -euo pipefail
docker exec docker-agents-lingxiao-1 bash -lc '
export CODEX_HOME=/home/node/.codex
export OPENAI_API_KEY="${DEEPSEEK_API_KEY:-gateway-local}"
unset OPENAI_BASE_URL
cd /home/node/agent-workspace/lingxiao

LOG=/tmp/app-server-identity-test.log
rm -f "$LOG"
timeout 90 codex app-server --listen ws://127.0.0.1:4510 >"$LOG" 2>&1 &
ASPID=$!
sleep 3
if ! kill -0 $ASPID 2>/dev/null; then
  echo "app-server failed to start:"
  cat "$LOG"
  exit 1
fi

python3 <<PY
import asyncio, json, websockets

async def main():
    uri = "ws://127.0.0.1:4510"
    async with websockets.connect(uri, max_size=10_000_000) as ws:
        init = {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"clientInfo":{"name":"test","version":"0"}}}
        await ws.send(json.dumps(init))
        print("init:", (await ws.recv())[:500])
        started = {"jsonrpc":"2.0","method":"initialized","params":{}}
        await ws.send(json.dumps(started))
        turn = {
            "jsonrpc":"2.0","id":2,"method":"turn/start",
            "params":{"input":[{"type":"text","text":"你是谁，一句话"}],"cwd":"/home/node/agent-workspace/lingxiao"}
        }
        await ws.send(json.dumps(turn))
        for _ in range(80):
            msg = await asyncio.wait_for(ws.recv(), timeout=60)
            print("evt:", msg[:800])
            if "turn/completed" in msg or "turn/failed" in msg or "error" in msg.lower():
                break

asyncio.run(main())
PY

kill $ASPID 2>/dev/null || true
'
