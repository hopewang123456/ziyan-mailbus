#!/usr/bin/env python3
"""Codex ↔ Mailbus A2A 桥。

Mailbus 出站 A2A 是「POST 事件文档」，Codex 容器没有 HTTP A2A 入口，通过
`docker exec <container> codex exec --skip-git-repo-check --json '<task>'`
执行，从 NDJSON 输出取最后一条 agent_message.text 作为结果。

  Mailbus 事件 ──POST /──▶ 本桥 ──docker exec──▶ Codex 容器
                                   └─结果──POST /api/a2a/messages──▶ Mailbus

环境变量：
  MAILBUS_API_URL        默认 http://172.28.0.1:9814
  MAILBUS_AGENTS_FILE    默认 /tokens/agents.json
                         每行 {name,agent_id,employee_id,token,container}
  BRIDGE_ENDPOINT        默认 http://172.28.0.1:9912/
  BRIDGE_PORT            默认 9912
  HEARTBEAT_INTERVAL_SEC 默认 60
  CODEX_TIMEOUT_SEC      默认 300
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAILBUS = os.environ.get("MAILBUS_API_URL", "http://172.28.0.1:9814").rstrip("/")
AGENTS_FILE = Path(os.environ.get("MAILBUS_AGENTS_FILE", "/tokens/agents.json"))
BRIDGE_ENDPOINT = os.environ.get("BRIDGE_ENDPOINT", "http://172.28.0.1:9912/")
PORT = int(os.environ.get("BRIDGE_PORT", "9912"))
HEARTBEAT_SEC = float(os.environ.get("HEARTBEAT_INTERVAL_SEC", "60"))
CODEX_TIMEOUT = float(os.environ.get("CODEX_TIMEOUT_SEC", "300"))

_seen: set[str] = set()
_lock = threading.Lock()
_by_employee: dict[str, dict] = {}
_by_agent: dict[str, dict] = {}
_by_name: dict[str, dict] = {}


def _log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def _load_agents() -> list[dict]:
    rows = json.loads(AGENTS_FILE.read_text(encoding="utf-8"))
    agents = [row for row in rows if row.get("token") and row.get("container")]
    _by_employee.clear()
    _by_agent.clear()
    _by_name.clear()
    for row in agents:
        if row.get("employee_id"):
            _by_employee[row["employee_id"]] = row
        if row.get("agent_id"):
            _by_agent[row["agent_id"]] = row
        _by_name[row.get("name", "")] = row
    return agents


def _post_json(url: str, body: dict, token: str | None = None, timeout: float = 15.0):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        return response.status, (json.loads(raw) if raw else None)


def _codex_run(container: str, text: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["docker", "exec", container, "codex", "exec",
             "--skip-git-repo-check", "--json", text],
            capture_output=True, text=True, timeout=CODEX_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False, f"Codex 超时（>{CODEX_TIMEOUT:.0f}s）"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    last_text = ""
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") == "item.completed":
            item = obj.get("item") or {}
            if item.get("type") == "agent_message" and item.get("text"):
                last_text = str(item["text"])
    if not last_text:
        err = (proc.stderr or "").strip()
        return False, f"无 agent_message（exit {proc.returncode}）: {err[:300]}"
    return True, last_text[:8000]


def _mailbus(token: str, body: dict) -> tuple[bool, str]:
    try:
        status, data = _post_json(f"{MAILBUS}/api/a2a/messages", body, token)
        return status in (200, 201), f"HTTP {status} {json.dumps(data, ensure_ascii=False) if data else ''}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _prompt(event: dict) -> str:
    payload = event.get("payload") or {}
    kind = str(event.get("kind") or "")
    title = payload.get("title") or payload.get("node_name") or "任务"
    body = payload.get("body") or ""
    lines = [
        "【Mailbus 事件】",
        f"kind: {kind}",
        f"task_id: {payload.get('task_id', '-')}",
        f"run_id: {payload.get('run_id', '-')}",
        f"attempt_no: {payload.get('attempt_no', '-')}",
        f"标题: {title}",
    ]
    if body:
        lines.append(f"正文: {body}")
    lines.append("请直接给出可验收的结果；本轮只回复结果正文。")
    return "\n".join(lines)


def _resolve_agent(event: dict) -> dict | None:
    payload = event.get("payload") or {}
    recipient = str(payload.get("recipient_id") or "")
    return _by_employee.get(recipient) or _by_agent.get(recipient) or _by_name.get(recipient)


def _handle_event(event: dict) -> None:
    event_id = str(event.get("event_id") or "")
    with _lock:
        if event_id and event_id in _seen:
            _log(f"重复事件忽略 {event_id}")
            return
        if event_id:
            _seen.add(event_id)
    agent = _resolve_agent(event)
    if agent is None:
        _log(f"未配置的接收人，事件 {event_id} 跳过")
        return
    payload = event.get("payload") or {}
    kind = str(event.get("kind") or "")
    ok, text = _codex_run(agent["container"], _prompt(event))
    name = agent.get("name") or agent.get("agent_id", "?")
    if not ok:
        _log(f"{name} Codex 调用失败: {text}")
        if kind == "task.assigned" and payload.get("run_id"):
            _mailbus(agent["token"], {
                "type": "result", "run_id": payload.get("run_id"),
                "attempt_no": payload.get("attempt_no"), "status": "failed",
                "output": json.dumps({"error": text}, ensure_ascii=False),
                "message_id": f"bridge-{event_id or int(time.time())}",
            })
        return
    _log(f"{name} Codex 返回 {len(text)} 字 (kind={kind})")
    if kind == "task.assigned" and payload.get("run_id"):
        accepted, detail = _mailbus(agent["token"], {
            "type": "result", "run_id": payload.get("run_id"),
            "attempt_no": payload.get("attempt_no"), "status": "completed",
            "output": text, "message_id": f"bridge-{event_id}",
        })
        _log(f"{name} result 上报 {'成功' if accepted else '失败'} {detail}")
        return
    hops = int(payload.get("bridge_hops") or 0)
    sender = payload.get("sender_id")
    if kind == "message.sent" and sender and hops < 1 and payload.get("kind") != "bridge-reply":
        accepted, detail = _mailbus(agent["token"], {
            "type": "message", "message_id": f"bridge-{event_id}",
            "body": text[:3900],
            "payload": {"recipient_id": sender, "channel": "a2a",
                        "bridge_hops": hops + 1, "kind": "bridge-reply"},
        })
        _log(f"{name} 回复上报 {'成功' if accepted else '失败'} {detail}")


def _heartbeat_once(agents: list[dict]) -> None:
    for agent in agents:
        body = {"type": "heartbeat", "endpoint": BRIDGE_ENDPOINT,
                "message_id": f"hb-codex-{agent.get('agent_id','?')[:8]}-{int(time.time())}"}
        ok, detail = _mailbus(agent["token"], body)
        if not ok:
            _log(f"{agent.get('name','?')} 心跳失败 {detail}")


def _heartbeat_loop() -> None:
    while True:
        try:
            agents = _load_agents()
        except Exception as exc:
            _log(f"读取 agents 文件失败: {exc}")
            agents = []
        if agents:
            _heartbeat_once(agents)
        time.sleep(HEARTBEAT_SEC)


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("/health", ""):
            self._reply(200, {"status": "ok", "service": "codex-a2a-bridge"})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") not in ("", "/dispatch"):
            self._reply(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            event = json.loads(self.rfile.read(length) or b"{}")
        except Exception as exc:
            self._reply(400, {"error": f"bad json: {exc}"})
            return
        threading.Thread(target=_handle_event, args=(event,), daemon=True).start()
        self._reply(202, {"accepted": True, "event_id": event.get("event_id")})

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    agents = _load_agents()
    _log(f"启动: codex mailbus={MAILBUS} endpoint={BRIDGE_ENDPOINT} agents={len(agents)}")
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    _log(f"监听 0.0.0.0:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
