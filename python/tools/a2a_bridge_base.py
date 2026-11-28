#!/usr/bin/env python3
"""Mailbus A2A 桥公共基类。

6 个框架桥（hermes / dsh / codex / openclaw / claude / opencode）共享同一套骨架：

  Mailbus 事件 ──POST /──▶ 本桥 ──框架调用──▶ 目标 Agent
                                  └─结果──POST /api/a2a/messages──▶ Mailbus

公共能力（本文件）：
  - agents.json 注册表加载与 employee_id / agent_id / name 反查
  - 事件去重（event_id）、task.assigned 结果回传、message.sent 回复
  - heartbeat 定时上报、HTTP 服务（/health 与 /dispatch）

子类只需声明少量配置常量并实现 run(agent, prompt) -> (ok, text)。
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_OUTPUT = 8000
MAX_REPLY_BODY = 3900


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


class BridgeBase:
    """A2A 桥公共骨架。子类最小实现：SERVICE / HB_PREFIX / DEFAULT_PORT +
    DEFAULT_ENDPOINT / REQUIRED_KEYS / run()。"""

    SERVICE = "a2a-bridge"
    HB_PREFIX = "bridge"
    DEFAULT_PORT = 9900
    DEFAULT_ENDPOINT = "http://172.28.0.1:9900/"
    # agents.json 每行必须具备的字段（缺任一则该行被跳过）
    REQUIRED_KEYS: tuple[str, ...] = ("token",)
    # 额外作为 name 别名索引的字段（如 hermes 的 profile）
    ALIAS_KEYS: tuple[str, ...] = ()
    # prompt 中是否输出 node_id 行
    PROMPT_NODE_ID = False
    # 框架调用超时（秒），子类可覆盖
    TIMEOUT_SEC = 300.0

    def __init__(self) -> None:
        self.api_url = os.environ.get("MAILBUS_API_URL", "http://172.28.0.1:9814").rstrip("/")
        self.agents_file = Path(os.environ.get("MAILBUS_AGENTS_FILE", "/tokens/agents.json"))
        self.endpoint = os.environ.get("BRIDGE_ENDPOINT", self.DEFAULT_ENDPOINT)
        self.port = int(os.environ.get("BRIDGE_PORT", str(self.DEFAULT_PORT)))
        self.heartbeat_sec = float(os.environ.get("HEARTBEAT_INTERVAL_SEC", "60"))
        self._seen: set[str] = set()
        self._lock = threading.Lock()
        self._by_employee: dict[str, dict] = {}
        self._by_agent: dict[str, dict] = {}
        self._by_name: dict[str, dict] = {}

    # ------------------------------------------------------------------ 子类实现
    def run(self, agent: dict, text: str) -> tuple[bool, str]:
        """调用目标框架执行任务，返回 (成功, 输出文本)。"""
        raise NotImplementedError

    def label(self, agent: dict) -> str:
        return str(agent.get("name") or agent.get("agent_id") or "?")

    # ------------------------------------------------------------------ 注册表
    def _row_ok(self, row: dict) -> bool:
        return all(row.get(key) for key in self.REQUIRED_KEYS)

    def load_agents(self) -> list[dict]:
        rows = json.loads(self.agents_file.read_text(encoding="utf-8"))
        agents = [row for row in rows if self._row_ok(row)]
        self._by_employee.clear()
        self._by_agent.clear()
        self._by_name.clear()
        for row in agents:
            if row.get("employee_id"):
                self._by_employee[row["employee_id"]] = row
            if row.get("agent_id"):
                self._by_agent[row["agent_id"]] = row
            if row.get("name"):
                self._by_name[row["name"]] = row
            for key in self.ALIAS_KEYS:
                if row.get(key):
                    self._by_name[row[key]] = row
        return agents

    def resolve_agent(self, event: dict) -> dict | None:
        recipient = str((event.get("payload") or {}).get("recipient_id") or "")
        return (
            self._by_employee.get(recipient)
            or self._by_agent.get(recipient)
            or self._by_name.get(recipient)
        )

    # ------------------------------------------------------------------ HTTP 出站
    def post_json(self, url: str, body: dict, token: str | None = None,
                  timeout: float = 15.0):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)

    def mailbus(self, token: str, body: dict) -> tuple[bool, str]:
        try:
            status, data = self.post_json(f"{self.api_url}/api/a2a/messages", body, token)
            text = json.dumps(data, ensure_ascii=False) if data else ""
            return status in (200, 201), f"HTTP {status} {text}"
        except urllib.error.HTTPError as exc:
            return False, f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001 - 网络异常统一降级
            return False, f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------ 事件处理
    def prompt(self, event: dict) -> str:
        payload = event.get("payload") or {}
        lines = [
            "【Mailbus 事件】",
            f"kind: {event.get('kind') or ''}",
            f"task_id: {payload.get('task_id', '-')}",
        ]
        if self.PROMPT_NODE_ID:
            lines.append(f"node_id: {payload.get('node_id', '-')}")
        lines.extend([
            f"run_id: {payload.get('run_id', '-')}",
            f"attempt_no: {payload.get('attempt_no', '-')}",
            f"标题: {payload.get('title') or payload.get('node_name') or '任务'}",
        ])
        body = payload.get("body") or ""
        if body:
            lines.append(f"正文: {body}")
        lines.append("请直接给出可验收的结果；本轮只回复结果正文。")
        return "\n".join(lines)

    def _claim_event(self, event_id: str) -> bool:
        """首次见到该 event_id 返回 True；重复事件返回 False。"""
        if not event_id:
            return True
        with self._lock:
            if event_id in self._seen:
                return False
            self._seen.add(event_id)
        return True

    def handle_event(self, event: dict) -> None:
        event_id = str(event.get("event_id") or "")
        if not self._claim_event(event_id):
            log(f"重复事件忽略 {event_id}")
            return
        agent = self.resolve_agent(event)
        if agent is None:
            log(f"未配置的接收人，事件 {event_id} 跳过")
            return
        payload = event.get("payload") or {}
        kind = str(event.get("kind") or "")
        name = self.label(agent)
        ok, text = self.run(agent, self.prompt(event))
        if not ok:
            log(f"{name} {self.SERVICE} 调用失败: {text}")
            self._report_failure(agent, payload, kind, event_id, text)
            return
        log(f"{name} 返回 {len(text)} 字 (kind={kind})")
        if kind == "task.assigned" and payload.get("run_id"):
            self._report_result(agent, payload, event_id, text)
            return
        self._report_reply(agent, payload, kind, event_id, text)

    def _report_failure(self, agent: dict, payload: dict, kind: str,
                        event_id: str, text: str) -> None:
        if kind != "task.assigned" or not payload.get("run_id"):
            return
        self.mailbus(agent["token"], {
            "type": "result",
            "run_id": payload.get("run_id"),
            "attempt_no": payload.get("attempt_no"),
            "status": "failed",
            "output": json.dumps({"error": text}, ensure_ascii=False),
            "message_id": f"bridge-{event_id or int(time.time())}",
        })

    def _report_result(self, agent: dict, payload: dict, event_id: str, text: str) -> None:
        accepted, detail = self.mailbus(agent["token"], {
            "type": "result",
            "run_id": payload.get("run_id"),
            "attempt_no": payload.get("attempt_no"),
            "status": "completed",
            "output": text,
            "message_id": f"bridge-{event_id}",
        })
        log(f"{self.label(agent)} result 上报 {'成功' if accepted else '失败'} {detail}")

    def _report_reply(self, agent: dict, payload: dict, kind: str,
                      event_id: str, text: str) -> None:
        hops = int(payload.get("bridge_hops") or 0)
        sender = payload.get("sender_id")
        if kind != "message.sent" or not sender or hops >= 1:
            return
        if payload.get("kind") == "bridge-reply":
            return
        accepted, detail = self.mailbus(agent["token"], {
            "type": "message",
            "message_id": f"bridge-{event_id}",
            "body": text[:MAX_REPLY_BODY],
            "payload": {
                "recipient_id": sender,
                "channel": "a2a",
                "bridge_hops": hops + 1,
                "kind": "bridge-reply",
            },
        })
        log(f"{self.label(agent)} 回复上报 {'成功' if accepted else '失败'} {detail}")

    # ------------------------------------------------------------------ 心跳
    def heartbeat_message_id(self, agent: dict) -> str:
        short = str(agent.get("agent_id") or "?")[:8]
        return f"hb-{self.HB_PREFIX}-{short}-{int(time.time())}"

    def heartbeat_once(self, agents: list[dict]) -> None:
        for agent in agents:
            body = {
                "type": "heartbeat",
                "endpoint": self.endpoint,
                "message_id": self.heartbeat_message_id(agent),
            }
            ok, detail = self.mailbus(agent["token"], body)
            if not ok:
                log(f"{self.label(agent)} 心跳失败 {detail}")

    def _heartbeat_loop(self) -> None:
        while True:
            try:
                agents = self.load_agents()
            except Exception as exc:  # noqa: BLE001 - 文件缺失不应终止桥
                log(f"读取 agents 文件失败: {exc}")
                agents = []
            if agents:
                self.heartbeat_once(agents)
            time.sleep(self.heartbeat_sec)

    # ------------------------------------------------------------------ HTTP 服务
    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        bridge = self

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
                    self._reply(200, {"status": "ok", "service": bridge.SERVICE})
                else:
                    self._reply(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                if self.path.rstrip("/") not in ("", "/dispatch"):
                    self._reply(404, {"error": "not found"})
                    return
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    event = json.loads(self.rfile.read(length) or b"{}")
                except Exception as exc:  # noqa: BLE001 - 非法请求体
                    self._reply(400, {"error": f"bad json: {exc}"})
                    return
                threading.Thread(
                    target=bridge.handle_event, args=(event,), daemon=True
                ).start()
                self._reply(202, {"accepted": True, "event_id": event.get("event_id")})

            def log_message(self, fmt: str, *args) -> None:
                return

        return Handler

    def serve(self) -> None:
        agents = self.load_agents()
        log(f"启动: {self.SERVICE} mailbus={self.api_url} "
            f"endpoint={self.endpoint} agents={len(agents)}")
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        server = ThreadingHTTPServer(("0.0.0.0", self.port), self._make_handler())
        log(f"监听 0.0.0.0:{self.port}")
        server.serve_forever()
