#!/usr/bin/env python3
"""OpenClaw ↔ Mailbus A2A 桥。

OpenClaw 容器的 gateway 因 session 迁移 / native service 问题无法启动，
但 `openclaw agent --local --agent <profile> --json --message-file ...`
可嵌入式执行（runner=embedded），无需 gateway。本桥通过 docker exec 调用。

  Mailbus 事件 ──POST /──▶ 本桥 ──docker exec openclaw agent──▶ OpenClaw 容器
                                   └─terminalReply.text──POST /api/a2a/messages──▶ Mailbus

环境变量：
  MAILBUS_API_URL        默认 http://172.28.0.1:9814
  MAILBUS_AGENTS_FILE    默认 /tokens/agents.json
                         每行 {name,agent_id,employee_id,token,profile}
  OPENCLAW_CONTAINER     默认 docker-agents-openclaw-1
  BRIDGE_ENDPOINT        默认 http://172.28.0.1:9913/
  BRIDGE_PORT            默认 9913
  HEARTBEAT_INTERVAL_SEC 默认 60
  OPENCLAW_TIMEOUT_SEC   默认 300
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
CONTAINER = os.environ.get("OPENCLAW_CONTAINER", "docker-agents-openclaw-1")
BRIDGE_ENDPOINT = os.environ.get("BRIDGE_ENDPOINT", "http://172.28.0.1:9913/")
PORT = int(os.environ.get("BRIDGE_PORT", "9913"))
HEARTBEAT_SEC = float(os.environ.get("HEARTBEAT_INTERVAL_SEC", "60"))
OPENCLAW_TIMEOUT = float(os.environ.get("OPENCLAW_TIMEOUT_SEC", "300"))
HOST_ENV_FILE = Path(os.environ.get(
    "MAILBUS_HOST_ENV", "/mnt/e/ai_tools/mailbus/shared/docker-agents/.env"))

_seen: set[str] = set()
_lock = threading.Lock()
_by_employee: dict[str, dict] = {}
_by_agent: dict[str, dict] = {}
_by_name: dict[str, dict] = {}


def _log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def _load_agents() -> list[dict]:
    rows = json.loads(AGENTS_FILE.read_text(encoding="utf-8"))
    agents = [row for row in rows if row.get("token") and row.get("profile")]
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


def _collect_terminal_replies(node, out: list[str]) -> None:
    if isinstance(node, dict):
        tr = node.get("terminalReply")
        if isinstance(tr, dict) and tr.get("text"):
            out.append(str(tr["text"]))
        for v in node.values():
            _collect_terminal_replies(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_terminal_replies(v, out)


def _read_host_deepseek_key() -> str:
    try:
        for line in HOST_ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _ensure_oc_keys() -> None:
    """容器 /tmp/oc-keys.env 重启即丢；缺失时从 host .env 自愈注入（stdin 传值，不暴露命令行）。"""
    try:
        chk = subprocess.run(["docker", "exec", CONTAINER, "sh", "-c", "test -s /tmp/oc-keys.env"],
                             capture_output=True, timeout=10)
        if chk.returncode == 0:
            return
    except Exception:
        return
    key = _read_host_deepseek_key()
    if not key:
        _log("WARN: host .env 无 DEEPSEEK_API_KEY，无法注入 openclaw key")
        return
    content = (f"export DEEPSEEK_API_KEY={key}\nexport OPENAI_API_KEY={key}\n"
               f"export GLM_API_KEY={key}\nexport ZHIPU_API_KEY={key}\n")
    try:
        subprocess.run(["docker", "exec", "-i", CONTAINER, "sh", "-c", "cat > /tmp/oc-keys.env"],
                       input=content, capture_output=True, text=True, timeout=10)
        _log("已自愈注入 openclaw /tmp/oc-keys.env")
    except Exception as exc:
        _log(f"注入 openclaw key 失败: {exc}")


def _openclaw_run(profile: str, text: str) -> tuple[bool, str]:
    _ensure_oc_keys()
    statedir = f"/workspace/data/.openclaw-{profile}"
    # prompt 走 stdin 写入容器临时文件，避免 shell 转义；key 从 /tmp/oc-keys.env 取（不暴露命令行）
    script = (
        "cat > /tmp/oc-prompt.txt && . /tmp/oc-keys.env; cd /workspace; "
        f"OPENCLAW_STATE_DIR={statedir} OPENCLAW_CONFIG_PATH={statedir}/openclaw.json "
        "OPENCLAW_NO_RESPAWN=1 CI=1 NO_COLOR=1 NODE_COMPILE_CACHE=/var/tmp/oc-cache "
        f"openclaw --no-color agent --local --agent {profile} --json --message-file /tmp/oc-prompt.txt"
    )
    try:
        proc = subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "sh", "-c", script],
            input=text, capture_output=True, text=True, timeout=OPENCLAW_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False, f"OpenClaw 超时（>{OPENCLAW_TIMEOUT:.0f}s）"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    out = proc.stdout or ""
    idx = out.find("{")
    result = ""
    if idx >= 0:
        try:
            obj, _ = json.JSONDecoder().raw_decode(out[idx:])
            replies: list[str] = []
            _collect_terminal_replies(obj, replies)
            if replies:
                result = replies[-1]
        except Exception:
            pass
    if not result:
        err = (proc.stderr or out or "").strip()
        return False, f"无 terminalReply（exit {proc.returncode}）: {err[-400:]}"
    return True, result[:8000]


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
    ok, text = _openclaw_run(agent["profile"], _prompt(event))
    name = agent.get("name") or agent.get("agent_id", "?")
    if not ok:
        _log(f"{name} OpenClaw 调用失败: {text}")
        if kind == "task.assigned" and payload.get("run_id"):
            _mailbus(agent["token"], {
                "type": "result", "run_id": payload.get("run_id"),
                "attempt_no": payload.get("attempt_no"), "status": "failed",
                "output": json.dumps({"error": text}, ensure_ascii=False),
                "message_id": f"bridge-{event_id or int(time.time())}",
            })
        return
    _log(f"{name} OpenClaw 返回 {len(text)} 字 (kind={kind})")
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
                "message_id": f"hb-openclaw-{agent.get('agent_id','?')[:8]}-{int(time.time())}"}
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
            self._reply(200, {"status": "ok", "service": "openclaw-a2a-bridge"})
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
    _log(f"启动: openclaw mailbus={MAILBUS} endpoint={BRIDGE_ENDPOINT} container={CONTAINER} agents={len(agents)}")
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    _log(f"监听 0.0.0.0:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
