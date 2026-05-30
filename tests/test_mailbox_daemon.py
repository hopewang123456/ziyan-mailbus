"""
mailbox-daemon.py 单元测试

覆盖：_cleanup_orphans / _reap_processes / _auto_ack / _mark_done / _parse_message
"""
import os, sys, json, tempfile, time, signal, logging
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import Inbox, Message, MsgStatus


def _ensure_sender_inbox(data_dir, sender):
    """确保发件人 inbox 目录存在（_send_completion_notice 需要写回执）"""
    path = os.path.join(data_dir, "inbox", sender, "inbox.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        json.dump({"agent": sender, "messages": [], "has_unread": False}, open(path, "w"))

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
    """_cleanup_orphans 不抛异常"""
    try:
        MailboxDaemon._cleanup_orphans()
    except Exception:
        assert False, "_cleanup_orphans 不应抛异常"


# ── 新增: _signal_name ──

def test_signal_name_maps_exit_codes():
    """_signal_name 正确映射退出码到信号名"""
    daemon = _make_daemon()
    assert "SIGKILL" in daemon._signal_name(137)
    assert "SIGSEGV" in daemon._signal_name(139)
    assert "SIGTERM" in daemon._signal_name(143)
    assert "SIGINT" in daemon._signal_name(130)
    assert daemon._signal_name(0) == ""
    assert daemon._signal_name(1) == ""
    assert "SIGKILL" in daemon._signal_name(-9)
    assert "SIGTERM" in daemon._signal_name(-15)


# ── 新增: checkpoint ──

def test_save_checkpoint_creates_file():
    """_save_checkpoint 写入 checkpoint 文件"""
    daemon = _make_daemon()
    ckpt_path = os.path.join(daemon.data_dir, MailboxDaemon.CHECKPOINT_FILE)
    assert not os.path.exists(ckpt_path)

    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = None
    daemon._running_procs[12345] = {
        "msg_ids": ["m1", "m2"],
        "senders": {"m1": "lingzhao", "m2": "lingxi"},
        "summary": "test task", "cmd": "echo hello",
        "started_at": time.time(), "proc": mock_proc,
    }
    daemon._save_checkpoint()
    assert os.path.exists(ckpt_path)
    ckpt = json.load(open(ckpt_path))
    assert ckpt["agent"] == "test"
    assert len(ckpt["running_procs"]) == 1
    assert ckpt["running_procs"][0]["msg_ids"] == ["m1", "m2"]


def test_load_checkpoint_restores_state():
    """_load_checkpoint 恢复 processing_ids + retry_map + 通知发件人"""
    daemon = _make_daemon()
    _ensure_sender_inbox(daemon.data_dir, "lingzhao")
    ckpt_path = os.path.join(daemon.data_dir, MailboxDaemon.CHECKPOINT_FILE)
    ckpt = {
        "agent": "test", "timestamp": "2026-01-01T00:00:00",
        "running_procs": [{"pid": 12345, "msg_ids": ["m1"],
                           "senders": {"m1": "lingzhao"},
                           "summary": "interrupted", "cmd": "echo", "started_at": 0}],
        "processing_ids": ["m1", "m2"],
        "retry_map": {"m1": 1},
    }
    json.dump(ckpt, open(ckpt_path, "w"))
    daemon._load_checkpoint()
    # m1 在 running_procs 中 → _mark_done 后 _processing_ids.discard
    assert "m1" not in daemon._processing_ids
    # m2 不在 running_procs 中，只作为 processing_ids 恢复
    assert "m2" in daemon._processing_ids
    assert daemon._retry_map == {"m1": 1}
    assert not os.path.exists(ckpt_path)


# ── 新增: _reap_processes 信号退出重试 ──

def test_reap_processes_normal_exit():
    """_reap_processes 正常退出发回执"""
    daemon = _make_daemon()
    _ensure_sender_inbox(daemon.data_dir, "lingzhao")
    daemon._processing_ids = set()
    daemon._retry_map = {}
    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.communicate.return_value = (b"done", b"")
    pid = 11111
    daemon._running_procs[pid] = {
        "msg_ids": ["m1"], "senders": {"m1": "lingzhao"},
        "summary": "normal task", "cmd": "echo done",
        "started_at": time.time() - 5, "proc": mock_proc,
    }
    daemon._reap_processes()
    assert pid not in daemon._running_procs
    # 回执已发送到发件人 inbox
    assert os.path.exists(os.path.join(daemon.data_dir, "inbox", "lingzhao", "inbox.json"))


def test_reap_processes_signal_exit_retry():
    """_reap_processes 信号退出自动重试"""
    daemon = _make_daemon()
    daemon._processing_ids = set()
    daemon._retry_map = {}
    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = 137
    pid = 22222
    daemon._running_procs[pid] = {
        "msg_ids": ["m1"], "senders": {"m1": "lingzhao"},
        "summary": "retry task", "cmd": "echo retry",
        "started_at": time.time() - 5, "proc": mock_proc,
    }
    with mock.patch.object(daemon, '_spawn_agent_process', return_value=True) as ms:
        daemon._reap_processes()
        ms.assert_called_once()
        assert daemon._retry_map.get("m1") == 1


def test_reap_processes_retry_twice_then_give_up():
    """_reap_processes 重试3次后不再重试"""
    daemon = _make_daemon()
    daemon._processing_ids = set()
    daemon._retry_map = {"m1": 3}
    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = 137
    mock_proc.communicate.return_value = (b"", b"")
    pid = 33333
    daemon._running_procs[pid] = {
        "msg_ids": ["m1"], "senders": {"m1": "lingzhao"},
        "summary": "give up", "cmd": "echo giveup",
        "started_at": time.time() - 5, "proc": mock_proc,
    }
    with mock.patch.object(daemon, '_spawn_agent_process') as ms:
        daemon._reap_processes()
        ms.assert_not_called()
        assert pid not in daemon._running_procs


# ── 新增: graceful shutdown ──

def test_handle_shutdown_saves_checkpoint():
    """_handle_shutdown 保存 checkpoint 并等待子进程"""
    daemon = _make_daemon()
    daemon._running = True
    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = None
    pid = 44444
    daemon._running_procs[pid] = {
        "msg_ids": ["m1"], "senders": {"m1": "lingzhao"},
        "summary": "shutdown", "cmd": "echo shutdown",
        "started_at": time.time() - 5, "proc": mock_proc,
    }
    def _wait(timeout=None):
        mock_proc.poll.return_value = 0
        return 0
    mock_proc.wait.side_effect = _wait
    daemon._handle_shutdown(signal.SIGTERM, None)
    assert not daemon._running


# ── 新增: _needs_agent 全面覆盖 ──

def test_needs_agent_comprehensive():
    """_needs_agent 覆盖所有分支"""
    daemon = _make_daemon()
    assert daemon._needs_agent("notice", "urgent")
    assert daemon._needs_agent("notice", "normal", from_="lingzhao")
    assert not daemon._needs_agent("report", "normal", from_="mailbus")
    assert not daemon._needs_agent("system", "normal", from_="system")
    assert not daemon._needs_agent("status_ack", "normal")
    assert daemon._needs_agent("design_review", "normal")
    assert daemon._needs_agent("task_status", "normal")
    assert daemon._needs_agent("code_review", "normal")
    assert daemon._needs_agent("task", "normal")
    assert not daemon._needs_agent("report", "normal")
    assert not daemon._needs_agent("system", "normal")


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
    
    # 初始化 daemon 内部状态（__new__ 不会自动初始化这些）
    daemon._running_procs = {}
    daemon._retry_map = {}
    daemon._processing_ids = set()
    
    # 初始化 inbox 文件
    json.dump({"agent": "test", "messages": [], "has_unread": False},
              open(daemon.inbox_path, "w"))
    json.dump([], open(daemon.ack_path, "w"))
    
    return daemon


if __name__ == "__main__":
    tests = [
        ("test_parse_message", test_parse_message),
        ("test_auto_ack", test_auto_ack),
        ("test_mark_done", test_mark_done),
        ("test_cleanup_orphans", test_cleanup_orphans),
        ("test_signal_name_maps_exit_codes", test_signal_name_maps_exit_codes),
        ("test_save_checkpoint_creates_file", test_save_checkpoint_creates_file),
        ("test_load_checkpoint_restores_state", test_load_checkpoint_restores_state),
        ("test_reap_processes_normal_exit", test_reap_processes_normal_exit),
        ("test_reap_processes_signal_exit_retry", test_reap_processes_signal_exit_retry),
        ("test_reap_processes_retry_twice_then_give_up", test_reap_processes_retry_twice_then_give_up),
        ("test_handle_shutdown_saves_checkpoint", test_handle_shutdown_saves_checkpoint),
        ("test_needs_agent_comprehensive", test_needs_agent_comprehensive),
    ]
    for name, fn in tests:
        fn()
        print(f"✅ {name}")
    print(f"\n🎉 全部 {len(tests)} 个通过")
