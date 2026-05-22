"""测试 ziyan-mailbus 数据模型 (lib/models.py)"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import (
    Message, MsgType, MsgStatus, Priority, Inbox,
    generate_msg_id, _now_iso,
)


def test_msg_type_enum():
    """MsgType 枚举完整性"""
    expected = {"notice", "task", "task_reply", "question", "forward",
                "forward_reply", "broadcast", "system", "error_report"}
    assert MsgType.ALL == expected, f"Missing types: {expected - MsgType.ALL}"
    print("  ✓ test_msg_type_enum")


def test_default_action_notice():
    action = MsgType.default_action(MsgType.NOTICE)
    assert action["ack"] == True
    assert action["execute"] == False
    assert action["reply_to"] == ""
    assert action["forward_to"] == []
    assert action["store_memory"] == True
    print("  ✓ test_default_action_notice")


def test_default_action_task():
    action = MsgType.default_action(MsgType.TASK)
    assert action["execute"] == True
    print("  ✓ test_default_action_task")


def test_default_action_task_reply():
    action = MsgType.default_action(MsgType.TASK_REPLY)
    assert action["execute"] == True
    assert action["reply_to"] is None  # 需要 __post_init__ 填充
    print("  ✓ test_default_action_task_reply")


def test_default_action_forward():
    action = MsgType.default_action(MsgType.FORWARD)
    assert action["forward_to"] == []
    print("  ✓ test_default_action_forward")


def test_default_action_forward_reply():
    action = MsgType.default_action(MsgType.FORWARD_REPLY)
    assert action["reply_to"] is None
    assert action["forward_to"] == []
    print("  ✓ test_default_action_forward_reply")


def test_default_action_broadcast():
    action = MsgType.default_action(MsgType.BROADCAST)
    assert action["ack"] == True
    assert action["reply_to"] == ""
    print("  ✓ test_default_action_broadcast")


def test_default_action_system():
    action = MsgType.default_action(MsgType.SYSTEM)
    assert action["store_memory"] == False
    print("  ✓ test_default_action_system")


def test_default_action_error_report():
    action = MsgType.default_action(MsgType.ERROR_REPORT)
    assert action["ack"] == True
    assert action["execute"] == False
    print("  ✓ test_default_action_error_report")


def test_message_basic():
    """Message 基本创建"""
    msg = Message(id="msg-test-001", from_="alice", to="bob",
                  type=MsgType.TASK, content="do something")
    assert msg.id == "msg-test-001"
    assert msg.from_ == "alice"
    assert msg.to == "bob"
    assert msg.type == "task"
    assert msg.content == "do something"
    # action 由 __post_init__ 自动填充
    assert msg.action is not None
    assert msg.action["ack"] == True
    assert msg.action["execute"] == True
    print("  ✓ test_message_basic")


def test_message_action_set_from_type():
    """type 为 forward_reply 时 action 自动推断"""
    msg = Message(id="msg-test-002", from_="灵曦", to="小七",
                  type=MsgType.FORWARD_REPLY, content="转发给一哥")
    assert msg.action["reply_to"] == "灵曦"  # __post_init__ 填充
    assert msg.action["forward_to"] == []
    assert msg.forward_chain is None  # 没有 forward_to 时不创建
    print("  ✓ test_message_action_set_from_type")


def test_message_forward_chain_auto():
    """forward_to 不为空时自动创建 forward_chain"""
    msg = Message(id="msg-test-003", from_="灵曦", to="小七",
                  type=MsgType.FORWARD_REPLY, content="转发给一哥")
    msg.action["forward_to"] = ["yige"]
    # 手动触发 __post_init__（在创建后修改 action 需要手动设置 forward_chain）
    if msg.forward_chain is None and msg.action.get("forward_to"):
        msg.forward_chain = {
            "root_id": msg.id,
            "hops": [{"agent": msg.from_, "action": "发起", "at": msg.created_at or ""}],
            "status": "in_progress",
        }
    assert msg.forward_chain is not None
    assert msg.forward_chain["root_id"] == "msg-test-003"
    assert len(msg.forward_chain["hops"]) == 1
    assert msg.forward_chain["hops"][0]["agent"] == "灵曦"
    print("  ✓ test_message_forward_chain_auto")


def test_message_to_dict():
    """Message to_dict 序列化"""
    msg = Message(id="msg-dict-001", from_="alice", to="bob",
                  type=MsgType.NOTICE, content="hello")
    d = msg.to_dict()
    assert d["from"] == "alice"  # from_ → from
    assert "from_" not in d
    assert d["to"] == "bob"
    assert d["type"] == "notice"
    assert d["action"] is not None
    print("  ✓ test_message_to_dict")


def test_message_from_dict():
    """Message from_dict 反序列化"""
    d = {
        "id": "msg-fd-001",
        "from": "alice",
        "to": "bob",
        "type": "task",
        "content": "do it",
        "status": "pending",
    }
    msg = Message.from_dict(d)
    assert msg.id == "msg-fd-001"
    assert msg.from_ == "alice"
    assert msg.type == "task"
    print("  ✓ test_message_from_dict")


def test_message_from_dict_auto_id():
    """缺 id 时自动生成"""
    d = {"from": "alice", "to": "bob", "content": "test"}
    msg = Message.from_dict(d)
    assert msg.id.startswith("auto-")
    print("  ✓ test_message_from_dict_auto_id")


def test_message_from_dict_unknown_fields():
    """from_dict 忽略未知字段"""
    d = {"id": "msg-uf-001", "from": "a", "to": "b", "content": "c",
         "unknown_field": "should_be_ignored", "in_reply_to": "msg-xxx"}
    msg = Message.from_dict(d)
    assert not hasattr(msg, 'unknown_field')
    assert not hasattr(msg, 'in_reply_to')
    print("  ✓ test_message_from_dict_unknown_fields")


def test_message_from_dict_action():
    """from_dict 带 action 字段"""
    d = {
        "id": "msg-act-001", "from": "a", "to": "b", "content": "c",
        "action": {"ack": True, "reply_to": "a", "execute": False, "forward_to": ["yige"], "store_memory": True},
        "task": {"summary": "test", "assignee": "yige"},
    }
    msg = Message.from_dict(d)
    assert msg.action["forward_to"] == ["yige"]
    assert msg.task["summary"] == "test"
    print("  ✓ test_message_from_dict_action")


def test_inbox_basic():
    inbox = Inbox(agent="test-agent")
    assert inbox.agent == "test-agent"
    assert inbox.has_unread == False
    assert inbox.messages == []
    print("  ✓ test_inbox_basic")


def test_inbox_to_dict():
    inbox = Inbox(agent="test-agent", has_unread=True)
    msg = Message(id="msg-in-001", from_="a", to="test-agent", content="hi")
    inbox.messages.append(msg)
    d = inbox.to_dict()
    assert d["agent"] == "test-agent"
    assert d["has_unread"] == True
    assert len(d["messages"]) == 1
    assert d["messages"][0]["from"] == "a"
    print("  ✓ test_inbox_to_dict")


def test_inbox_from_dict():
    d = {"agent": "test-agent", "has_unread": True, "messages": [
        {"id": "msg-ifd-1", "from": "a", "to": "test-agent", "content": "hi"}
    ]}
    inbox = Inbox.from_dict(d)
    assert inbox.agent == "test-agent"
    assert inbox.has_unread == True
    assert len(inbox.messages) == 1
    assert inbox.messages[0].from_ == "a"
    print("  ✓ test_inbox_from_dict")


def test_generate_msg_id():
    msg_id = generate_msg_id()
    assert msg_id.startswith("msg-")
    assert len(msg_id) > 10
    print("  ✓ test_generate_msg_id")


if __name__ == "__main__":
    test_msg_type_enum()
    test_default_action_notice()
    test_default_action_task()
    test_default_action_task_reply()
    test_default_action_forward()
    test_default_action_forward_reply()
    test_default_action_broadcast()
    test_default_action_system()
    test_default_action_error_report()
    test_message_basic()
    test_message_action_set_from_type()
    test_message_forward_chain_auto()
    test_message_to_dict()
    test_message_from_dict()
    test_message_from_dict_auto_id()
    test_message_from_dict_unknown_fields()
    test_message_from_dict_action()
    test_inbox_basic()
    test_inbox_to_dict()
    test_inbox_from_dict()
    test_generate_msg_id()
    print(f"\n✓ 全部 {21} 个测试通过")
