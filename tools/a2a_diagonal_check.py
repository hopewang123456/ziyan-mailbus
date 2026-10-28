"""A2A 双栈对角对拍（CI 化，D13-③）— runbook docs/runbooks/a2a-diagonal-smoke.md 的脚本化。

对角语义：与 python/java HttpA2AClient 逐字对齐的 0.2 请求形状（双侧单测钉死）
分别打 java / python 的 **SDK 面**（POST /api/a2a/sdk/{agent}），断言双方输出
同款官方裸 Task 形状（id/contextId/status.state/artifacts/history/metadata）。

    python tools/a2a_diagonal_check.py --py http://127.0.0.1:9816 --java http://127.0.0.1:9815

前置：双 serve 已起；python store 需 allow_write_without_token（冒烟 config）。
退出码：0 全部通过；非零为首处失败。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import uuid


def _rpc(base_url: str, agent: str, method: str, params: dict) -> tuple[int, dict]:
    url = f"{base_url.rstrip('/')}/api/a2a/sdk/{agent}"
    payload = json.dumps({"jsonrpc": "2.0", "id": str(uuid.uuid4())[:8],
                          "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _send(base_url: str, agent: str, task_id: str, intent: str) -> dict:
    """0.2 请求形状（HttpA2AClient.send_message 钉死形状；0.3 名亦可，服务端归一）。"""
    _, out = _rpc(base_url, agent, "message/send", {"message": {
        "messageId": f"msg-{task_id}", "role": "ROLE_USER",
        "parts": [{"text": intent}],
        "metadata": {"mailbus": {"taskId": task_id,
                                 "planned_chain": [{"role_type": 1}]}},
    }})
    return out


def _stream_first_frames(base_url: str, agent: str, task_id: str, intent: str, n: int = 2) -> list[dict]:
    """message/stream SSE：读前 n 个 data 帧即断开（http.client 行级读）。"""
    import http.client
    from urllib.parse import urlparse

    url = f"{base_url.rstrip('/')}/api/a2a/sdk/{agent}"
    parts = urlparse(url)
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=20)
    payload = json.dumps({"jsonrpc": "2.0", "id": "sse-1", "method": "message/stream",
                          "params": {"message": {
                              "messageId": f"msg-{task_id}", "role": "ROLE_USER",
                              "parts": [{"text": intent}],
                              "metadata": {"mailbus": {"taskId": task_id,
                                                       "planned_chain": [{"role_type": 1}]}}}}}).encode()
    conn.request("POST", parts.path, body=payload,
                 headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    resp = conn.getresponse()
    frames = []
    buf = ""
    while resp.status == 200 and len(frames) < n:
        line = resp.fp.readline().decode("utf-8", "replace")
        if not line:
            break
        if line.startswith("data:"):
            buf += line[5:].strip()
        elif line.strip() == "" and buf:
            frames.append(json.loads(buf))
            buf = ""
    conn.close()
    return frames


def check(label: str, cond: bool, detail: str = "") -> None:
    if not cond:
        print(f"[FAIL] {label}: {detail}", file=sys.stderr)
        sys.exit(1)
    print(f"[ok] {label}")


def _assert_sdk_task(side: str, task: dict, tid: str, want_state: str) -> None:
    check(f"{side} id", task.get("id") == tid, str(task))
    state = ((task.get("status") or {}).get("state")) or ""
    check(f"{side} status.state={want_state}", state == want_state, str(task))
    check(f"{side} contextId", task.get("contextId") == tid, str(task))
    check(f"{side} artifacts/history", task.get("artifacts") == [] and task.get("history") == [], str(task))
    mailbus = (task.get("metadata") or {}).get("mailbus") or {}
    check(f"{side} metadata.mailbus.taskId", mailbus.get("taskId") == tid, str(task))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--py", required=True, help="python serve base URL")
    ap.add_argument("--java", required=True, help="java serve base URL")
    ap.add_argument("--py-agent", default="agentX")
    ap.add_argument("--java-agent", default="agentA")
    args = ap.parse_args()

    for side, base, agent in (("java", args.java, args.java_agent), ("py", args.py, args.py_agent)):
        # 幂等：随机后缀避免重跑 task_exists（CI 全新 store，本地重跑友好）
        run = uuid.uuid4().hex[:6]
        tid = f"ext-diag-{side}-sdk-{run}-1"

        # 1) message/send（0.3 名）：官方裸 Task + WORKING
        out = _send(base, agent, tid, "对角 SDK 面冒烟")
        check(f"{side} send jsonrpc-ok", "error" not in out, str(out))
        _assert_sdk_task(f"{side} send", out.get("result") or {}, tid, "TASK_STATE_WORKING")

        # 2) tasks/get：待批 → INPUT_REQUIRED + hq 上下文
        code, got = _rpc(base, agent, "tasks/get", {"id": tid})
        check(f"{side} get http200", code == 200, str(code))
        _assert_sdk_task(f"{side} get", got.get("result") or {}, tid, "TASK_STATE_INPUT_REQUIRED")
        rmb = (((got.get("result") or {}).get("metadata") or {}).get("mailbus") or {})
        check(f"{side} get hqType=plan_approval", rmb.get("hqType") == "plan_approval", str(got))

        # 3) tasks/cancel（第二个任务）：取消后 SDK Task 形状 CANCELED
        tid2 = f"ext-diag-{side}-sdk-{run}-2"
        _send(base, agent, tid2, "对角取消")
        code, cancelled = _rpc(base, agent, "tasks/cancel", {"id": tid2})
        check(f"{side} cancel http200", code == 200, str(code))
        _assert_sdk_task(f"{side} cancel", cancelled.get("result") or {}, tid2, "TASK_STATE_CANCELED")

        # 4) message/stream SSE：帧为 SDK statusEvent 形状（taskId/status.state，无 final）
        tid3 = f"ext-diag-{side}-sdk-{run}-3"
        frames = _stream_first_frames(base, agent, tid3, "对角 SSE 帧形状", n=2)
        check(f"{side} sse got-frames", len(frames) >= 1, str(frames))
        first = (frames[0].get("result") or {}) if frames else {}
        check(f"{side} sse frame.taskId", first.get("taskId") == tid3, str(first))
        st = (first.get("status") or {}).get("state") or ""
        check(f"{side} sse frame.state", st in ("TASK_STATE_WORKING", "TASK_STATE_INPUT_REQUIRED"), str(first))
        check(f"{side} sse frame.no-final", "final" not in first, str(first))
        check(f"{side} sse frame.contextId", first.get("contextId") == tid3, str(first))

    print("A2A diagonal SDK-face parity: ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
