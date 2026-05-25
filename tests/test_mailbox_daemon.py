"""
mailbox-daemon.py 单元测试

覆盖：_cleanup_orphans / _reap_processes / _auto_ack / _mark_done / _parse_message
"""
import os, sys, json, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import Inbox, Message, MsgStatus

# mailbox-daemon.py 有连字符，用 importlib 加载
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "mailbox_daemon",
    os.path.join(os.path.dirname(__file__), "..", "mailbox-daemon.py")
)
_mbox = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mbox)
MailboxDaemon = _mbox.MailboxDaemon


def test_parse_message():
    """_parse_message 兼容 dict 和 Message 对象"""
    daemon = _make_daemon()
    
    # dict 输入
    result = daemon._parse_message({"id": "m1", "content": "hello", "type": "task"})
    assert result["id"] == "m1"
    assert result["body"]["content"] == "hello"
    
    # Message 对象输入
    msg = Message(id="m2", from_="test", to="test", content="world", type="notice",
                  priority="normal", status=MsgStatus.PENDING, created_at="2026-01-01")
    result = daemon._parse_message(msg)
    assert result["id"] == "m2"
    assert "world" in result["body"]["content"]


def test_auto_ack():
    """_auto_ack 写入 ack 并更新消息状态"""
    daemon = _make_daemon()
    msg_id = "test-ack-001"
    
    # 先写入一条消息到 inbox
    inbox = Inbox(agent="test")
    inbox.messages.append(Message(
        id=msg_id, from_="test", to="test", content="test", type="task", priority="normal",
        status=MsgStatus.PENDING, created_at="2026-01-01"
    ))
    inbox.has_unread = True
    json.dump(inbox.to_dict(), open(daemon.inbox_path, "w"))
    
    daemon._auto_ack(msg_id)
    
    # 检查 ack 文件
    ack = json.load(open(daemon.ack_path))
    assert any(e["msg_id"] == msg_id for e in (ack if isinstance(ack, list) else [ack]))
    
    # 检查消息状态
    inbox2 = Inbox.from_dict(json.load(open(daemon.inbox_path)))
    m = inbox2.get_msg(msg_id)
    assert m is not None
    assert inbox2.msg_field(m, "status") == MsgStatus.ACKNOWLEDGED


def test_mark_done():
    """_mark_done 设置 state=done + done_note"""
    daemon = _make_daemon()
    msg_id = "test-done-001"
    
    inbox = Inbox(agent="test")
    inbox.messages.append(Message(
        id=msg_id, from_="test", to="test", content="done test", type="task", priority="normal",
        status=MsgStatus.ACKNOWLEDGED, created_at="2026-01-01"
    ))
    json.dump(inbox.to_dict(), open(daemon.inbox_path, "w"))
    
    daemon._mark_done(msg_id, "处理完成")
    
    inbox2 = Inbox.from_dict(json.load(open(daemon.inbox_path)))
    m = inbox2.get_msg(msg_id)
    assert inbox2.msg_field(m, "state") == "done"
    assert inbox2.msg_field(m, "done_note") == "处理完成"


def test_cleanup_orphans():
    """_cleanup_orphans 不抛异常（集成测试时验证实际清理）"""
    try:
        MailboxDaemon._cleanup_orphans()
    except Exception:
        assert False, "_cleanup_orphans 不应抛异常"


def _make_daemon():
    """创建测试用 daemon 实例"""
    tmp = tempfile.mkdtemp(prefix="mailbus_test_")
    daemon = MailboxDaemon.__new__(MailboxDaemon)
    daemon.agent_name = "test"
    daemon.data_dir = tmp
    daemon.inbox_path = os.path.join(tmp, "inbox", "test", "inbox.json")
    daemon.ack_path = os.path.join(tmp, "inbox", "test", "ack.json")
    os.makedirs(os.path.dirname(daemon.inbox_path), exist_ok=True)
    
    import logging
    daemon.log = logging.getLogger("test_daemon")
    daemon.log.addHandler(logging.NullHandler())
    
    # 初始化 inbox 文件
    json.dump({"agent": "test", "messages": [], "has_unread": False},
              open(daemon.inbox_path, "w"))
    json.dump([], open(daemon.ack_path, "w"))
    
    return daemon


if __name__ == "__main__":
    test_parse_message()
    print("✅ test_parse_message")
    test_auto_ack()
    print("✅ test_auto_ack")
    test_mark_done()
    print("✅ test_mark_done")
    test_cleanup_orphans()
    print("✅ test_cleanup_orphans")
    print("\n🎉 全部通过")
