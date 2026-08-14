"""测试告警系统 (lib/alerter.py)"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.ops.alerter import push_alert, get_recent_alerts, load_alerts


def test_push_and_get():
    with tempfile.TemporaryDirectory() as td:
        push_alert(td, "agent_offline", "critical", "agent-f",
                   "agent-f 离线超过3次心跳")
        alerts = get_recent_alerts(td)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "agent_offline"
        assert alerts[0]["severity"] == "critical"
        assert alerts[0]["agent"] == "agent-f"
    print("  ✓ test_push_and_get")


def test_multiple_alerts():
    with tempfile.TemporaryDirectory() as td:
        push_alert(td, "disk_full", "warn", "system", "磁盘空间不足")
        push_alert(td, "key_missing", "critical", "agent-e", "API Key 缺失")
        push_alert(td, "agentmemory_down", "critical", "system", "AM 断联")

        alerts = get_recent_alerts(td, limit=10)
        assert len(alerts) == 3
        assert alerts[-1]["type"] == "agentmemory_down"
        assert alerts[0]["type"] == "disk_full"
    print("  ✓ test_multiple_alerts")


def test_alerts_cap():
    """告警上限 100 条"""
    with tempfile.TemporaryDirectory() as td:
        for i in range(150):
            push_alert(td, "test", "info", "system", f"test alert {i}")
        alerts = get_recent_alerts(td, limit=200)
        assert len(alerts) <= 100
    print("  ✓ test_alerts_cap")


def test_push_to_admin_missing():
    """无管理员时不应抛异常"""
    with tempfile.TemporaryDirectory() as td:
        # 不创建 config.json
        push_alert(td, "test", "info", "system", "test")
        # 不应该抛异常
        alerts = get_recent_alerts(td)
        assert len(alerts) == 1
    print("  ✓ test_push_to_admin_missing")


def test_alert_dedupe():
    """同 type+agent 的 active 告警不重复写入"""
    with tempfile.TemporaryDirectory() as td:
        push_alert(td, "key_missing", "critical", "agent-e", "API Key 缺失")
        push_alert(td, "key_missing", "critical", "agent-e", "API Key 缺失 again")
        alerts = load_alerts(td)
        assert len(alerts["alerts"]) == 1
    print("  ✓ test_alert_dedupe")


if __name__ == "__main__":
    test_push_and_get()
    test_multiple_alerts()
    test_alerts_cap()
    test_push_to_admin_missing()
    test_alert_dedupe()
    print(f"\n✓ 全部 {5} 个测试通过")
