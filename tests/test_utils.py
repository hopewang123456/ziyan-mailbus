"""测试工具函数 (lib/utils.py)"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.utils import (
    json_read, json_write, build_message, generate_msg_id,
    resolve_paths, log_error,
)
from lib.models import MsgType, MsgStatus


def test_json_write_and_read():
    with tempfile.TemporaryDirectory() as td:
        fp = os.path.join(td, "test.json")
        data = {"key": "value", "num": 42}
        json_write(fp, data)
        loaded = json_read(fp)
        assert loaded["key"] == "value"
        assert loaded["num"] == 42
    print("  ✓ test_json_write_and_read")


def test_json_read_not_found():
    assert json_read("/tmp/nonexistent_file_xyz.json") is None
    assert json_read("/tmp/nonexistent_file_xyz.json", {}) == {}
    print("  ✓ test_json_read_not_found")


def test_build_message_basic():
    msg = build_message("alice", "bob", "hello", MsgType.NOTICE)
    assert msg.from_ == "alice"
    assert msg.to == "bob"
    assert msg.content == "hello"
    assert msg.type == "notice"
    assert msg.status == MsgStatus.PENDING
    assert msg.id.startswith("msg-")
    print("  ✓ test_build_message_basic")


def test_build_message_with_forward():
    msg = build_message("灵瑾", "小七", "转发给一哥",
                        MsgType.FORWARD_REPLY, forward_to=["yige"])
    assert msg.action["forward_to"] == ["yige"]
    assert msg.type == "forward_reply"
    print("  ✓ test_build_message_with_forward")


def test_build_message_with_task():
    msg = build_message("灵瑾", "一哥", "请整理安全规范",
                        MsgType.TASK_REPLY,
                        task={"summary": "安全规范", "assignee": "一哥"})
    assert msg.task["summary"] == "安全规范"
    assert msg.task["assignee"] == "一哥"
    print("  ✓ test_build_message_with_task")


def test_build_message_priority_urgent():
    msg = build_message("a", "b", "紧急情况", MsgType.NOTICE, priority="urgent")
    assert msg.priority == "urgent"
    print("  ✓ test_build_message_priority_urgent")


def test_generate_msg_id():
    msg_id = generate_msg_id()
    assert msg_id.startswith("msg-")
    parts = msg_id.split("-")
    assert len(parts) == 3
    assert len(parts[1]) == 8  # YYYYMMDD
    print("  ✓ test_generate_msg_id")


def test_resolve_paths():
    with tempfile.TemporaryDirectory() as td:
        paths = resolve_paths(td)
        assert "inbox" in paths
        assert "queue_urgent" in paths
        assert "queue_normal" in paths
        assert "archive" in paths
        assert "errors" in paths
        assert "sent" in paths
        assert "board" in paths
        assert "config" in paths
        assert paths["sent"] == f"{td}/sent.json"
        assert paths["config"] == f"{td}/config.json"
    print("  ✓ test_resolve_paths")


def test_log_error():
    with tempfile.TemporaryDirectory() as td:
        log_error(td, "msg-001", "agent-a", "CLI 推送失败")
        log_error(td, "msg-002", "agent-b", "超时")
        week = os.listdir(td)[0]
        with open(os.path.join(td, week)) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert "msg-001" in lines[0]
        assert "msg-002" in lines[1]
    print("  ✓ test_log_error")


if __name__ == "__main__":
    test_json_write_and_read()
    test_json_read_not_found()
    test_build_message_basic()
    test_build_message_with_forward()
    test_build_message_with_task()
    test_build_message_priority_urgent()
    test_generate_msg_id()
    test_resolve_paths()
    test_log_error()
    print(f"\n✓ 全部 {9} 个测试通过")
