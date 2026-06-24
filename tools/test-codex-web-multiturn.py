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

def wait_reply(tid, label):
    for i in range(60):
        time.sleep(2)
        read = rpc("thread/read", {"threadId": tid, "includeTurns": True})
        turns = read.get("result", {}).get("thread", {}).get("turns") or []
        texts = []
        for t in turns:
            for item in t.get("items") or []:
                if isinstance(item.get("text"), str):
                    texts.append(item["text"])
        if len(texts) >= label:
            return texts[-1]
    raise TimeoutError(label)

start = rpc("thread/start", {"cwd": CWD})
tid = start["result"]["thread"]["id"]
print("thread", tid)

for msg in ["你好，你是谁", "灵霄呢"]:
    print("USER:", msg)
    rpc("turn/start", {"threadId": tid, "input": [{"type": "text", "text": msg}]})
    reply = wait_reply(tid, 1 if msg.startswith("你好") else 2)
    print("REPLY:", reply[:500])
    if "Failed" in reply or "error" in reply.lower():
        raise SystemExit(1)

print("PASS multi-turn")
