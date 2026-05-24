"""测试任务追踪 (lib/tracker.py)"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.tracker import TaskTracker


def test_create():
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        task = t.create("task-test-001", summary="测试", assignee="小七")
        assert task["task_id"] == "task-test-001"
        assert task["status"] == "pending"
        assert task["summary"] == "测试"
        assert task["assignee"] == "小七"
    print("  ✓ test_create")


def test_get():
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-get-001")
        task = t.get("task-get-001")
        assert task is not None
        assert task["task_id"] == "task-get-001"
        assert t.get("nonexistent") is None
    print("  ✓ test_get")


def test_update_status():
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-upd-001")
        t.update_status("task-upd-001", "running")
        assert t.get("task-upd-001")["status"] == "running"
        t.update_status("task-upd-001", "success")
        assert t.get("task-upd-001")["status"] == "success"
    print("  ✓ test_update_status")


def test_update_status_with_error():
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-err-001")
        t.update_status("task-err-001", "failed",
                        {"code": "TIMEOUT", "reason": "超时"})
        task = t.get("task-err-001")
        assert task["status"] == "failed"
        assert task["error"]["code"] == "TIMEOUT"
    print("  ✓ test_update_status_with_error")


def test_add_hop():
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-hop-001", chain_hops=[{"agent": "灵瑾", "action": "发起"}])
        t.add_hop("task-hop-001", "小七", "转发给一哥")
        t.add_hop("task-hop-001", "一哥", "执行并回复")
        task = t.get("task-hop-001")
        assert len(task["chain"]) == 3
        assert task["chain"][0]["agent"] == "灵瑾"
        assert task["chain"][1]["agent"] == "小七"
        assert task["chain"][2]["agent"] == "一哥"
    print("  ✓ test_add_hop")


def test_increment_reminder():
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-rem-001")
        assert t.increment_reminder("task-rem-001") == 1
        assert t.increment_reminder("task-rem-001") == 2
        assert t.get("task-rem-001")["reminded_count"] == 2
    print("  ✓ test_increment_reminder")


def test_check_reminders_normal():
    """催办没到时不应触发"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-norm-001", assignee="小七")
        t.update_status("task-norm-001", "running")
        agents = {"小七": {"name": "小七"}}
        # reminder_minutes=5，刚创建不可能超过 5 分钟
        escalated = t.check_reminders(agents, reminder_minutes=5)
        assert len(escalated) == 0
    print("  ✓ test_check_reminders_normal")


def test_check_reminders_trigger():
    """催办触发"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-trig-001", summary="需要催办", assignee="小七")
        t.update_status("task-trig-001", "running")
        agents = {"小七": {"name": "小七"}}
        # 设 reminder_minutes=0，立刻触发
        escalated = t.check_reminders(agents, reminder_minutes=0)
        assert len(escalated) == 1
        assert escalated[0]["task_id"] == "task-trig-001"
    print("  ✓ test_check_reminders_trigger")


def test_check_reminders_timeout():
    """催办超限自动 timeout"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-to-001", assignee="小七")
        t.update_status("task-to-001", "running")
        t.increment_reminder("task-to-001")
        t.increment_reminder("task-to-001")
        t.increment_reminder("task-to-001")
        t.increment_reminder("task-to-001")  # 已超过 max_reminders=3
        agents = {"小七": {"name": "小七"}}
        escalated = t.check_reminders(agents, reminder_minutes=0, max_reminders=3)
        task = t.get("task-to-001")
        assert task["status"] == "timeout"
        assert len(escalated) == 0  # 超限后不再返回催办
    print("  ✓ test_check_reminders_timeout")


def test_list_all():
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-la-001")
        t.create("task-la-002")
        t.update_status("task-la-002", "running")
        all_tasks = t.list_all()
        assert len(all_tasks) == 2
        running = t.list_all(status_filter="running")
        assert len(running) == 1
    print("  ✓ test_list_all")


if __name__ == "__main__":
    test_create()
    test_get()
    test_update_status()
    test_update_status_with_error()
    test_add_hop()
    test_increment_reminder()
    test_check_reminders_normal()
    test_check_reminders_trigger()
    test_check_reminders_timeout()
    test_list_all()
    print(f"\n✓ 全部 {10} 个测试通过")
