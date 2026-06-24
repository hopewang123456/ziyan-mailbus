#!/usr/bin/env python3
import json
import sys
import time
import urllib.request

PORT = 7681
CWD = sys.argv[1] if len(sys.argv) > 1 else "/home/node/agent-workspace/lingjian"
NEED = sys.argv[2] if len(sys.argv) > 2 else "灵鉴"


def rpc(method, params=None):
    body = json.dumps({"method": method, "params": params or {}}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/codex-api/rpc",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


start = rpc("thread/start", {"cwd": CWD})
thread = start["result"]["thread"]
tid = thread["id"]
print("thread", tid, "cwd", thread.get("cwd"))

rpc(
    "turn/start",
    {
        "threadId": tid,
        "input": [{"type": "text", "text": "你是谁？用一句话回答"}],
    },
)

for i in range(60):
    time.sleep(2)
    read = rpc("thread/read", {"threadId": tid, "includeTurns": True})
    turns = read.get("result", {}).get("thread", {}).get("turns") or []
    texts = []
    for t in turns:
        for item in t.get("items") or []:
            if isinstance(item.get("text"), str):
                texts.append(item["text"])
            msg = item.get("message") or item.get("content")
            if isinstance(msg, str):
                texts.append(msg)
    if texts:
        reply = "\n".join(texts)
        print("REPLY:", reply[:800])
        if NEED in reply:
            print("PASS")
            sys.exit(0)
        if "OpenAI" in reply or ("Codex" in reply and NEED not in reply):
            print("FAIL generic")
            sys.exit(1)
        print("PASS (no generic codex phrase)")
        sys.exit(0)
    print(f"wait {i + 1} turns={len(turns)}")

print("TIMEOUT")
sys.exit(1)
