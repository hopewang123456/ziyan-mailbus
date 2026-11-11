"""D16 批4：双栈并跑验收（消息存储 SoT 统一后）。

用法（仓库根，两个 serve 指向同一 data-dir）：
    python tools/d16_dual_write_check.py \
        --py http://127.0.0.1:9816 --java http://127.0.0.1:9815 \
        --py-agent agentX --java-agent agentA

检查：
  1. java 发 → python 读（java 写 inbox.json，python 直读可见）
  2. python 发 → java 读（java 投影读 inbox.json）
  3. 并发写 10+10（跨语言锁互斥，无丢消息/无重复 id）
  4. java ack 一条 python 发的消息 → python 直读看得到 state=done（写回 SoT）
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import urllib.request


def _req(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def inbox(base: str, agent: str) -> dict:
    return _req("GET", f"{base}/api/inbox/{agent}")


def ids(doc: dict) -> list[str]:
    return [m.get("id") for m in doc.get("messages", [])]


def java_send(base: str, agent: str, content: str) -> str:
    return _req("POST", f"{base}/api/inbox/{agent}/send",
                {"from": agent, "content": content})["id"]


def py_send(base: str, agent: str, content: str, sender: str = "api") -> str:
    resp = _req("POST", f"{base}/api/send-msg",
                {"to": agent, "from": sender, "content": content})
    return resp.get("msg_id") or resp["id"]


def main() -> int:
    ap = argparse.ArgumentParser(description="D16 双栈消息读写验收")
    ap.add_argument("--py", default="http://127.0.0.1:9816")
    ap.add_argument("--java", default="http://127.0.0.1:9815")
    ap.add_argument("--py-agent", default="agentX")
    ap.add_argument("--java-agent", default="agentA")
    ap.add_argument("--n", type=int, default=10)
    args = ap.parse_args()

    failures: list[str] = []

    # 1. java 发 → python 读
    jid = java_send(args.java, args.py_agent, "from-java")
    if jid not in ids(inbox(args.py, args.py_agent)):
        failures.append(f"java 发的 {jid} python 读不到")

    # 2. python 发 → java 读
    pid = py_send(args.py, args.java_agent, "from-python", sender=args.py_agent)
    if pid not in ids(inbox(args.java, args.java_agent)):
        failures.append(f"python 发的 {pid} java 读不到")

    # 3. 并发写（两栈同时打同一对 agent）
    sent_java: list[str] = []
    sent_py: list[str] = []
    errors: list[str] = []

    def hit_java() -> None:
        try:
            for i in range(args.n):
                sent_java.append(java_send(args.java, args.py_agent, f"par-java-{i}"))
        except Exception as e:  # noqa: BLE001 - 验收脚本，保留原始错误
            errors.append(f"java: {e}")

    def hit_py() -> None:
        try:
            for i in range(args.n):
                sent_py.append(py_send(args.py, args.java_agent, f"par-py-{i}",
                                       sender=args.py_agent))
        except Exception as e:  # noqa: BLE001
            errors.append(f"python: {e}")

    threads = [threading.Thread(target=hit_java), threading.Thread(target=hit_py)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    failures.extend(errors)

    py_ids = ids(inbox(args.py, args.py_agent))
    java_ids = ids(inbox(args.java, args.java_agent))
    missing_java = [i for i in sent_java if i not in py_ids]
    missing_py = [i for i in sent_py if i not in java_ids]
    if missing_java:
        failures.append(f"并发 java 写丢失: {missing_java[:3]}")
    if missing_py:
        failures.append(f"并发 python 写 java 读不到: {missing_py[:3]}")
    if len(py_ids) != len(set(py_ids)) or len(java_ids) != len(set(java_ids)):
        failures.append("出现重复消息 id（锁失效或 id 撞号）")

    # 4. java ack 写回 SoT：python 直读应看到 status=acknowledged；
    #    state 只有在 pending/空 时才推进（python process_ack 语义），
    #    已被 python pusher 置 pushed 的保持 pushed。
    ack_id = java_send(args.java, args.py_agent, "ack-probe")
    _req("POST", f"{args.java}/api/inbox/ack/{ack_id}")
    probe = next((m for m in inbox(args.py, args.py_agent)["messages"]
                  if m.get("id") == ack_id), None)
    if probe is None:
        failures.append(f"java ack 的消息 {ack_id} python 读不到")
    else:
        if probe.get("status") != "acknowledged":
            failures.append(f"java ack 后 python 读到 status={probe.get('status')}")
        if probe.get("state") not in ("done", "pushed"):
            failures.append(f"java ack 后 python 读到 state={probe.get('state')}")

    print(f"java→py {jid} | py→java {pid} | 并发 {len(sent_java)}+{len(sent_py)} | "
          f"py inbox {len(py_ids)} | java inbox {len(java_ids)}")
    if failures:
        for f in failures:
            print("FAIL:", f)
        return 1
    print("DUAL-STACK MESSAGE SoT:", "OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
