"""测试心跳检测 (lib/heartbeat.py)"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.heartbeat import (
    load_status, save_status, is_online,
    check_inbox_size, check_disk_space,
)


def test_load_status_empty():
    with tempfile.TemporaryDirectory() as td:
        status = load_status(td)
        assert "agents" in status
        assert "health" in status
    print("  ✓ test_load_status_empty")


def test_save_and_load():
    with tempfile.TemporaryDirectory() as td:
        save_status(td, {"agents": {"test": {"status": "online"}}})
        status = load_status(td)
        assert status["agents"]["test"]["status"] == "online"
    print("  ✓ test_save_and_load")


def test_is_online_default():
    with tempfile.TemporaryDirectory() as td:
        assert is_online(td, "unknown-agent") == True
    print("  ✓ test_is_online_default")


def test_is_online_offline():
    with tempfile.TemporaryDirectory() as td:
        save_status(td, {"agents": {"test-offline": {"status": "offline"}}})
        assert is_online(td, "test-offline") == False
    print("  ✓ test_is_online_offline")


def test_is_online_online():
    with tempfile.TemporaryDirectory() as td:
        save_status(td, {"agents": {"test-online": {"status": "online"}}})
        assert is_online(td, "test-online") == True
    print("  ✓ test_is_online_online")


def test_check_inbox_size_empty():
    """空 inbox 不告警"""
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(f"{td}/inbox/test-agent")
        with open(f"{td}/inbox/test-agent/inbox.json", "w") as f:
            json.dump({"agent": "test-agent", "messages": [], "has_unread": False}, f)
        warnings = check_inbox_size(td, {"test-agent": {}}, warn_limit=10)
        assert len(warnings) == 0
    print("  ✓ test_check_inbox_size_empty")


def test_check_inbox_size_warn():
    """超过告警阈值的 inbox"""
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(f"{td}/inbox/test-agent")
        msgs = [{"id": f"msg-{i}", "content": "test"} for i in range(15)]
        with open(f"{td}/inbox/test-agent/inbox.json", "w") as f:
            json.dump({"agent": "test-agent", "messages": msgs, "has_unread": True}, f)
        warnings = check_inbox_size(td, {"test-agent": {}}, warn_limit=10)
        assert len(warnings) == 1
        assert warnings[0]["agent"] == "test-agent"
        assert warnings[0]["count"] == 15
    print("  ✓ test_check_inbox_size_warn")


def test_check_disk_space():
    """磁盘检测不抛异常"""
    with tempfile.TemporaryDirectory() as td:
        result = check_disk_space(td, warn_mb=1000)
        assert result["status"] == "ok"  # 空目录肯定小于 1000MB
        assert result["size_mb"] < 1
    print("  ✓ test_check_disk_space")


def test_heartbeat_scan_no_agents():
    """无 agent 时不抛异常"""
    from lib.heartbeat import heartbeat_scan
    with tempfile.TemporaryDirectory() as td:
        changes = heartbeat_scan({}, {}, td, interval=0)
        assert changes == []
    print("  ✓ test_heartbeat_scan_no_agents")


if __name__ == "__main__":
    test_load_status_empty()
    test_save_and_load()
    test_is_online_default()
    test_is_online_offline()
    test_is_online_online()
    test_check_inbox_size_empty()
    test_check_inbox_size_warn()
    test_check_disk_space()
    test_heartbeat_scan_no_agents()
    print(f"\n✓ 全部 {9} 个测试通过")
