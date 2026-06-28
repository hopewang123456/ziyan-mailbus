import json, time, urllib.request

PORT = 7681
CWD = "/home/node/agent-workspace/lingxiao"

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
print("thread", tid)
print("provider", start["result"].get("modelProvider"), "model", start["result"].get("model"))
print("cwd", thread.get("cwd"))

rpc("turn/start", {
    "threadId": tid,
    "input": [{"type": "text", "text": "你是谁，一句话"}],
})

for i in range(60):
    time.sleep(2)
    read = rpc("thread/read", {"threadId": tid, "includeTurns": True})
    turns = read.get("result", {}).get("thread", {}).get("turns") or []
    status = (read.get("result", {}).get("thread", {}).get("status") or {}).get("type")
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
        if "灵霄" in reply:
            print("PASS")
            raise SystemExit(0)
        if "Codex CLI" in reply:
            print("FAIL generic")
            raise SystemExit(1)
        print("PASS ambiguous")
        raise SystemExit(0)
    print(f"wait {i+1} status={status} turns={len(turns)}")

print("TIMEOUT")
raise SystemExit(1)
