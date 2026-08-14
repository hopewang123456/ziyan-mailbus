"""
lib/commands.py 单元测试

覆盖: _cleanup_stale_locks / session 锁清理机制
"""
import os, sys, json, tempfile, time, glob
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.infra.utils import configure_stdio_utf8

configure_stdio_utf8()

from lib.application.commands.commands import _cleanup_stale_locks
from lib.infra.constants import DEFAULT_DATA_DIR
from lib.infra.utils import get_lock_root


# ════════════════════════════════════════════════════════════════
# P0#4: session 锁清理机制验证
# ════════════════════════════════════════════════════════════════


def _create_tmp_lock(prefix: str, suffix: str = ".lock", age: float = 0) -> str:
    """在锁目录创建一个测试锁文件，返回路径"""
    fname = prefix if suffix and prefix.endswith(suffix) else f"{prefix}{suffix}"
    fpath = os.path.join(get_lock_root(), fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("test")
    old_time = time.time() - age
    os.utime(fpath, (old_time, old_time))
    return fpath


def test_cleanup_stale_mailbus_locks():
    """_cleanup_stale_locks: 清理超过 max_age 的 mailbus 锁文件"""
    old_lock = _create_tmp_lock("mailbus-aaaa.lock", age=600)
    new_lock = _create_tmp_lock("mailbus-bbbb.lock", age=10)
    try:
        _cleanup_stale_locks(max_age=300)
        assert not os.path.exists(old_lock), "过期 mailbus 锁文件应被清理"
        assert os.path.exists(new_lock), "未过期的 mailbus 锁文件应保留"
    finally:
        for p in [old_lock, new_lock]:
            try: os.unlink(p)
            except OSError: pass


def test_cleanup_stale_skips_recent_locks():
    """_cleanup_stale_locks: max_age 内的锁文件不清理"""
    recent = _create_tmp_lock("mailbus-cccc.lock", age=60)
    try:
        _cleanup_stale_locks(max_age=300)
        assert os.path.exists(recent), "60秒前的锁文件应保留"
    finally:
        try: os.unlink(recent)
        except OSError: pass


def test_cleanup_stale_session_locks():
    """_cleanup_stale_locks: 清理 session 级 .lock（含 session/agent 关键字）"""
    session_lock = _create_tmp_lock("session-abc.lock", age=600)
    agent_lock = _create_tmp_lock("agent-task-run.lock", age=600)
    unrelated_lock = _create_tmp_lock("chrome-123.lock", age=600)
    try:
        _cleanup_stale_locks(max_age=300)
        assert not os.path.exists(session_lock), "session 锁应被清理"
        assert not os.path.exists(agent_lock), "agent 锁应被清理"
        assert os.path.exists(unrelated_lock), "无关锁应保留"
    finally:
        for p in [session_lock, agent_lock, unrelated_lock]:
            try: os.unlink(p)
            except OSError: pass


def test_cleanup_stale_db_shm_wal():
    """_cleanup_stale_locks: 清理 .db-shm / .db-wal 残留"""
    shm_file = _create_tmp_lock("hermes-session.db-shm", age=600)
    wal_file = _create_tmp_lock("task-queue.db-wal", age=600)
    try:
        _cleanup_stale_locks(max_age=300)
        assert not os.path.exists(shm_file), ".db-shm 残留应被清理"
        assert not os.path.exists(wal_file), ".db-wal 残留应被清理"
    finally:
        for p in [shm_file, wal_file]:
            try: os.unlink(p)
            except OSError: pass


def test_cleanup_stale_agentmemory_locks():
    """_cleanup_stale_locks: 清理 agentmemory 残留锁文件"""
    sock_file = _create_tmp_lock("agentmemory-test.sock", age=600)
    try:
        _cleanup_stale_locks(max_age=300)
        assert not os.path.exists(sock_file), "agentmemory socket 应被清理"
    finally:
        try: os.unlink(sock_file)
        except OSError: pass


def test_cleanup_stale_inbox_lock_files():
    """_cleanup_stale_locks: 清理 inbox 目录下残留的 .lock / .tmp"""
    test_inbox = os.path.join(DEFAULT_DATA_DIR, "inbox", "_test_cleanup")
    os.makedirs(test_inbox, exist_ok=True)
    old_lock = os.path.join(test_inbox, "writing.lock")
    old_tmp = os.path.join(test_inbox, "data.tmp")
    old_json = os.path.join(test_inbox, "inbox.json")
    for fpath in [old_lock, old_tmp, old_json]:
        with open(fpath, "w") as f:
            f.write("test")
        old_time = time.time() - 600
        os.utime(fpath, (old_time, old_time))
    try:
        _cleanup_stale_locks(max_age=300)
        assert not os.path.exists(old_lock), "inbox .lock 应被清理"
        assert not os.path.exists(old_tmp), "inbox .tmp 应被清理"
        assert os.path.exists(old_json), "inbox .json 不应被清理"
    finally:
        for fpath in [old_lock, old_tmp, old_json]:
            try: os.unlink(fpath)
            except OSError: pass
        try: os.rmdir(test_inbox)
        except OSError: pass


def test_cleanup_stale_handles_nonexistent_inbox():
    """_cleanup_stale_locks: inbox 目录不存在时不应抛异常"""
    with mock.patch.object(os.path, 'isdir', return_value=False):
        try:
            _cleanup_stale_locks()
        except Exception as e:
            assert False, f"inbox 不存在时不应抛异常: {e}"


def test_cleanup_stale_no_files_to_clean():
    """_cleanup_stale_locks: 无文件时静默通过"""
    lock_root = get_lock_root()
    for pattern in [
        os.path.join(lock_root, "mailbus-*.lock"),
        os.path.join(lock_root, "session-*.lock"),
        os.path.join(lock_root, "hermes-*.db-shm"),
        os.path.join(lock_root, "agentmemory-*.sock"),
    ]:
        for f in glob.glob(pattern):
            try: os.unlink(f)
            except OSError: pass
    try:
        _cleanup_stale_locks(max_age=300)
    except Exception as e:
        assert False, f"无文件清理时不应抛异常: {e}"


if __name__ == "__main__":
    tests = [
        ("test_cleanup_stale_mailbus_locks", test_cleanup_stale_mailbus_locks),
        ("test_cleanup_stale_skips_recent_locks", test_cleanup_stale_skips_recent_locks),
        ("test_cleanup_stale_session_locks", test_cleanup_stale_session_locks),
        ("test_cleanup_stale_db_shm_wal", test_cleanup_stale_db_shm_wal),
        ("test_cleanup_stale_agentmemory_locks", test_cleanup_stale_agentmemory_locks),
        ("test_cleanup_stale_inbox_lock_files", test_cleanup_stale_inbox_lock_files),
        ("test_cleanup_stale_handles_nonexistent_inbox", test_cleanup_stale_handles_nonexistent_inbox),
        ("test_cleanup_stale_no_files_to_clean", test_cleanup_stale_no_files_to_clean),
    ]
    for name, fn in tests:
        fn()
        print(f"✅ {name}")
    print(f"\n🎉 全部 {len(tests)} 个通过")
