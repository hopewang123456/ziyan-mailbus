#!/usr/bin/env python3
"""
回归自测：验证 API send-msg 推送和 ack 流程

测试场景：
1. HTTP API send-msg → 消息写入目标 inbox
2. 扫描流程（scan）→ 识别未读消息
3. Agent 写 ack → 总线扫描 ack → 状态更新
4. 边界：不存在的 agent、缺少字段、空消息
"""

import os
import sys
import json
import time
import tempfile
import threading
import http.client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.infra.utils import configure_stdio_utf8

configure_stdio_utf8()

from lib.domain.models import Message, Inbox, MsgStatus, Priority, MsgType
from lib.infra.utils import json_read, json_write, resolve_paths, _now_iso, build_message
from lib.application.scan import build_queues, update_message_status
from lib.adapters.results.ack_handler import process_ack, scan_ack_files
from lib.api.base import MailbusAPIHandler as RealMailbusAPIHandler


TESTS_PASSED = 0
TESTS_FAILED = 0


class MockHandler:
    """模拟 HTTP 请求处理器，供 handle_send_msg 等调用"""
    data_dir = ""
    agents = {}
    command = "GET"
    path = "/"
    _resp = None

    def __init__(self, data_dir, agents, command="GET", path="/"):
        self.data_dir = data_dir
        self.agents = agents
        self.command = command
        self.path = path
        self._resp = None

    def _send_json(self, data, status=200):
        self._resp = (data, status)

    def _send_api_error(self, code, status=400, *, detail="", **extra):
        payload = {"error": detail or code, "error_code": code}
        if extra:
            payload.update(extra)
        self._send_json(payload, status)

    def _read_post_body(self):
        return {}


def _make_temp_env(agent_names=None):
    """创建临时 mailbus 环境"""
    tmp = tempfile.mkdtemp()
    inbox_dir = os.path.join(tmp, "inbox")
    if agent_names is None:
        agent_names = {"test_agent": {"name": "测试Agent", "type": "none"}}
    for name in agent_names:
        os.makedirs(os.path.join(inbox_dir, name), exist_ok=True)
        inbox_data = {
            "agent": name,
            "has_unread": False,
            "messages": [],
            "since": _now_iso(),
        }
        json_write(os.path.join(inbox_dir, name, "inbox.json"), inbox_data)
    return tmp, agent_names


def _read_inbox(data_dir, agent):
    path = os.path.join(data_dir, "inbox", agent, "inbox.json")
    return json_read(path, {})


def assert_eq(actual, expected, label):
    global TESTS_PASSED, TESTS_FAILED
    ok = actual == expected
    if ok:
        TESTS_PASSED += 1
        status = "✓"
    else:
        TESTS_FAILED += 1
        status = "✗"
    print(f"  {status} {label}: expected={expected!r}, actual={actual!r}")


def assert_gte(actual, expected_min, label):
    global TESTS_PASSED, TESTS_FAILED
    ok = actual >= expected_min
    if ok:
        TESTS_PASSED += 1
        status = "✓"
    else:
        TESTS_FAILED += 1
        status = "✗"
    print(f"  {status} {label}: {actual} >= {expected_min}")


def assert_true(actual, label):
    global TESTS_PASSED, TESTS_FAILED
    ok = bool(actual)
    if ok:
        TESTS_PASSED += 1
    else:
        TESTS_FAILED += 1
    print(f"  {'✓' if ok else '✗'} {label}: {actual!r}")


# ── Tests ──

def test_send_msg_api_writes_inbox():
    """Scenario 1: HTTP API send-msg 写入目标 inbox"""
    print("\n[Scenario 1] API send-msg → inbox 写入")
    tmp, agents = _make_temp_env()
    from lib.api.handlers_inbox import handle_send_msg

    mh = MockHandler(tmp, agents, "POST", "/api/send-msg")
    mh._post_body = {"to": "test_agent", "content": "回归自测消息", "from": "agent-f", "type": "task"}
    mh._read_post_body = lambda: mh._post_body
    handle_send_msg(mh)

    assert_eq(mh._resp[1], 200, "响应状态码 200")
    assert_true("msg_id" in mh._resp[0], "返回 msg_id")

    inbox_data = _read_inbox(tmp, "test_agent")
    assert_eq(inbox_data.get("has_unread"), True, "has_unread = True")
    assert_eq(len(inbox_data.get("messages", [])), 1, "1 条消息")
    msg = inbox_data["messages"][0]
    assert_eq(msg.get("content"), "回归自测消息", "消息内容正确")
    assert_eq(msg.get("from"), "agent-f", "发件人正确")
    assert_eq(msg.get("status"), "pending", "初始状态 pending")


def test_send_msg_api_missing_fields():
    """Scenario 2: 缺少必填字段返回 400"""
    print("\n[Scenario 2] API send-msg 缺少字段")
    tmp, agents = _make_temp_env()
    from lib.api.handlers_inbox import handle_send_msg

    mh = MockHandler(tmp, agents, "POST", "/api/send-msg")
    mh._post_body = {"to": "", "content": ""}
    mh._read_post_body = lambda: mh._post_body
    handle_send_msg(mh)

    assert_eq(mh._resp[1], 400, "缺少字段返回 400")
    assert_true("缺少" in mh._resp[0].get("error", ""), "错误信息含缺少提示")


def test_send_msg_api_unknown_agent():
    """Scenario 3: 不存在的 agent 返回 404"""
    print("\n[Scenario 3] API send-msg 不存在的 agent")
    tmp, agents = _make_temp_env()
    from lib.api.handlers_inbox import handle_send_msg

    mh = MockHandler(tmp, agents, "POST", "/api/send-msg")
    mh._post_body = {"to": "ghost_agent", "content": "测试"}
    mh._read_post_body = lambda: mh._post_body
    handle_send_msg(mh)

    assert_eq(mh._resp[1], 404, "未知 agent 返回 404")
    assert_true("ghost_agent" in mh._resp[0].get("error", ""), "错误提示包含 agent 名")


def test_ack_process_updates_status():
    """Scenario 4: Agent 写 ack → process_ack 更新状态"""
    print("\n[Scenario 4] ack 处理流程")
    tmp, agents = _make_temp_env()
    msg = build_message("agent-f", "test_agent", "回归测试消息")

    inbox_path = os.path.join(tmp, "inbox", "test_agent", "inbox.json")
    inbox_data = json_read(inbox_path, {})
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg.to_dict())
    json_write(inbox_path, inbox.to_dict())

    before = _read_inbox(tmp, "test_agent")
    assert_eq(len(before["messages"]), 1, "消息已写入")
    assert_eq(before["messages"][0].get("status"), "pending", "status = pending")

    ack_path = os.path.join(tmp, "inbox", "test_agent", "ack.json")
    ack_data = {"action": "ack", "msg_id": msg.id, "agent": "test_agent", "timestamp": _now_iso()}
    json_write(ack_path, [ack_data])

    count = scan_ack_files(tmp, agents)
    assert_eq(count, 1, "处理了 1 条 ack")

    after = _read_inbox(tmp, "test_agent")
    msg_after = after["messages"][0]
    assert_eq(msg_after.get("status"), "acknowledged", "status → acknowledged")

    ack_content = json_read(ack_path, [])
    assert_eq(ack_content, [], "ack.json 已清空")


def test_scan_builds_queue():
    """Scenario 5: scan 识别 pending 消息进入队列"""
    print("\n[Scenario 5] 扫描队列构建")
    tmp, agents = _make_temp_env()
    msg = build_message("agent-f", "test_agent", "待扫描消息", msg_type=MsgType.TASK)

    inbox_path = os.path.join(tmp, "inbox", "test_agent", "inbox.json")
    inbox_data = json_read(inbox_path, {})
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg.to_dict())
    json_write(inbox_path, inbox.to_dict())

    urgent, normal = build_queues(tmp, agents)
    all_normal = normal.get("test_agent", [])
    assert_gte(len(all_normal), 1, "待推送消息被识别到 normal 队列")


def test_ack_clears_unread_flag():
    """Scenario 6: 全部 ack 后 has_unread 自动变 false"""
    print("\n[Scenario 6] ack 后 unread 标记清除")
    tmp, agents = _make_temp_env()
    msg = build_message("agent-f", "test_agent", "最后一条")

    inbox_path = os.path.join(tmp, "inbox", "test_agent", "inbox.json")
    inbox_data = json_read(inbox_path, {})
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg.to_dict())
    json_write(inbox_path, inbox.to_dict())

    ack_path = os.path.join(tmp, "inbox", "test_agent", "ack.json")
    json_write(ack_path, [{"action": "ack", "msg_id": msg.id, "agent": "test_agent", "timestamp": _now_iso()}])
    scan_ack_files(tmp, agents)

    after = _read_inbox(tmp, "test_agent")
    # 非 task 的 notice → ack 后直接 done → has_unread = false
    assert_eq(after.get("has_unread"), False, "has_unread = false")


def test_full_roundtrip():
    """Scenario 7: 完整端到端流程 send → write → ack → status"""
    print("\n[Scenario 7] 完整端到端流程")
    tmp, agents = _make_temp_env()
    from lib.api.handlers_inbox import handle_send_msg

    mh = MockHandler(tmp, agents, "POST", "/api/send-msg")
    mh._post_body = {"to": "test_agent", "content": "E2E 回归测试", "from": "agent-f", "type": "task"}
    mh._read_post_body = lambda: mh._post_body
    handle_send_msg(mh)

    msg_id = mh._resp[0]["msg_id"]
    assert_eq(mh._resp[1], 200, "send-msg 成功")

    inbox_data = _read_inbox(tmp, "test_agent")
    assert_eq(len(inbox_data["messages"]), 1, "消息存在")
    assert_eq(inbox_data["messages"][0]["status"], "pending", "状态 pending")

    ack_path = os.path.join(tmp, "inbox", "test_agent", "ack.json")
    json_write(ack_path, [{"action": "ack", "msg_id": msg_id, "agent": "test_agent", "timestamp": _now_iso()}])

    count = scan_ack_files(tmp, agents)
    assert_eq(count, 1, "ack 已处理")

    final = _read_inbox(tmp, "test_agent")
    final_msg = final["messages"][0]
    assert_eq(final_msg.get("status"), "acknowledged", "最终状态 acknowledged")


def test_send_msg_api_get_method():
    """Scenario 8: GET 方法发送消息"""
    print("\n[Scenario 8] GET 方法 send-msg")
    tmp, agents = _make_temp_env()
    from lib.api.handlers_inbox import handle_send_msg

    mh = MockHandler(tmp, agents, "GET", "/api/send-msg?to=test_agent&content=GET测试&from=api_test")
    mh._read_post_body = lambda: {}
    handle_send_msg(mh)

    assert_eq(mh._resp[1], 200, "GET 方式返回 200")
    assert_true("msg_id" in mh._resp[0], "返回 msg_id")

    inbox_data = _read_inbox(tmp, "test_agent")
    assert_eq(inbox_data.get("has_unread"), True, "has_unread = True")
    assert_eq(inbox_data["messages"][0].get("content"), "GET测试", "GET 方式内容正确")


def test_api_status_endpoint():
    """Scenario 9: /api/status 端点可达"""
    print("\n[Scenario 9] API status 端点")
    tmp, agents = _make_temp_env()
    from lib.api.handlers_system import handle_status

    mh = MockHandler(tmp, agents, "GET", "/api/status")
    handle_status(mh)

    assert_eq(mh._resp[1], 200, "status 返回 200")
    assert_eq(mh._resp[0].get("agents"), 1, "1 个 agent")
    assert_true("total_messages" in mh._resp[0], "返回 total_messages")


def test_inbox_api_endpoint():
    """Scenario 10: GET /api/inbox/<agent> 读取 inbox"""
    print("\n[Scenario 10] API inbox 端点")
    tmp, agents = _make_temp_env()
    from lib.api.handlers_inbox import handle_inbox

    msg = build_message("agent-f", "test_agent", "inbox端点测试")
    inbox_path = os.path.join(tmp, "inbox", "test_agent", "inbox.json")
    inbox_data = json_read(inbox_path, {})
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg.to_dict())
    json_write(inbox_path, inbox.to_dict())

    mh = MockHandler(tmp, agents, "GET", "/api/inbox/test_agent")
    handle_inbox(mh, "test_agent")

    assert_eq(mh._resp[1], 200, "inbox 返回 200")
    assert_eq(mh._resp[0].get("agent"), "test_agent", "agent 名称正确")
    assert_gte(mh._resp[0].get("unread", 0), 1, "未读数 >= 1")
    assert_gte(len(mh._resp[0].get("messages", [])), 1, ">= 1 条消息")


def test_ack_forward_chain():
    """Scenario 11: 带 forward_chain 的 ack 处理"""
    print("\n[Scenario 11] forward_chain ack 处理")
    tmp, agents = _make_temp_env()
    msg = build_message("agent-f", "test_agent", "转发链测试")
    msg_dict = msg.to_dict()
    msg_dict["forward_chain"] = {
        "hops": [{"agent": "test_agent", "status": "pending"}, {"agent": "other", "status": "pending"}],
        "status": "active",
    }

    inbox_path = os.path.join(tmp, "inbox", "test_agent", "inbox.json")
    inbox_data = json_read(inbox_path, {})
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg_dict)
    json_write(inbox_path, inbox.to_dict())

    ack_path = os.path.join(tmp, "inbox", "test_agent", "ack.json")
    json_write(ack_path, [{"action": "ack", "msg_id": msg.id, "agent": "test_agent", "timestamp": _now_iso()}])
    scan_ack_files(tmp, agents)

    after = _read_inbox(tmp, "test_agent")
    chain = after["messages"][0].get("forward_chain", {})
    assert_eq(chain.get("status"), "active", "转发链 status 仍为 active（仅跳转一个）")
    hops = chain.get("hops", [])
    assert_eq(hops[0].get("status"), "done", "当前 agent 的 hop 已 done")


def main():
    print("=" * 60)
    print("  mailbus-mailbus send-msg & ack 回归自测")
    print("=" * 60)

    tests = [
        ("send-msg → inbox 写入", test_send_msg_api_writes_inbox),
        ("send-msg 缺少字段", test_send_msg_api_missing_fields),
        ("send-msg 未知 agent", test_send_msg_api_unknown_agent),
        ("ack 状态更新", test_ack_process_updates_status),
        ("scan 队列构建", test_scan_builds_queue),
        ("ack 清除 unread", test_ack_clears_unread_flag),
        ("完整端到端", test_full_roundtrip),
        ("GET 方式 send-msg", test_send_msg_api_get_method),
        ("API status 端点", test_api_status_endpoint),
        ("API inbox 端点", test_inbox_api_endpoint),
        ("forward_chain ack", test_ack_forward_chain),
    ]

    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  → {name}: PASS")
        except Exception as e:
            global TESTS_FAILED
            TESTS_FAILED += 1
            print(f"  → {name}: FAIL (异常: {e})")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    total = TESTS_PASSED + TESTS_FAILED
    if TESTS_FAILED == 0:
        print(f"  ✓ 全部通过 — {TESTS_PASSED} 个断言, 11 个场景")
        print("  回归自测: PASS")
        return 0
    else:
        print(f"  ✗ 失败 {TESTS_FAILED}/{total} 个断言")
        print("  回归自测: FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
