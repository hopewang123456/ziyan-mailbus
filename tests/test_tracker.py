"""测试任务追踪 (lib/tracker.py)"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.application.orchestration.tracker import TaskTracker
from lib.infra.utils import json_read


def test_create():
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        task = t.create("task-test-001", summary="测试", assignee="agent-c")
        assert task["task_id"] == "task-test-001"
        # 有 assignee 时会初始化 pipeline chain，任务直接进入 running 且需审计
        assert task["status"] == "running"
        assert task.get("requires_audit") is True
        assert task.get("chain") and len(task["chain"]) == 1
        assert task["summary"] == "测试"
        assert task["assignee"] == "agent-c"
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
        # add_hop 仍写 legacy {agent, action} 格式；首跳手动写入避免 pipeline 规范化
        from lib.infra.utils import json_write, _now_iso
        ts = _now_iso()
        json_write(t._task_path("task-hop-001"), {
            "task_id": "task-hop-001",
            "summary": "",
            "assignee": "agent-a",
            "status": "running",
            "chain": [{"agent": "agent-a", "action": "发起", "status": "done", "at": ts}],
            "requires_audit": False,
            "created_at": ts,
            "updated_at": ts,
        })
        t.add_hop("task-hop-001", "agent-c", "转发给agent-g")
        t.add_hop("task-hop-001", "agent-g", "执行并回复")
        task = t.get("task-hop-001")
        assert len(task["chain"]) == 3
        assert task["chain"][0]["agent"] == "agent-a"
        assert task["chain"][1]["agent"] == "agent-c"
        assert task["chain"][2]["agent"] == "agent-g"
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
        t.create("task-norm-001", assignee="agent-c")
        t.update_status("task-norm-001", "running")
        agents = {"agent-c": {"name": "agent-c"}}
        # reminder_minutes=5，刚创建不可能超过 5 分钟
        escalated = t.check_reminders(agents, reminder_minutes=5)
        assert len(escalated) == 0
    print("  ✓ test_check_reminders_normal")


def test_check_reminders_trigger():
    """催办触发"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-trig-001", summary="需要催办", assignee="agent-c")
        t.update_status("task-trig-001", "running")
        agents = {"agent-c": {"name": "agent-c"}}
        # 设 reminder_minutes=0，立刻触发
        escalated = t.check_reminders(agents, reminder_minutes=0)
        assert len(escalated) == 1
        assert escalated[0]["task_id"] == "task-trig-001"
    print("  ✓ test_check_reminders_trigger")


def test_check_reminders_timeout():
    """催办超限自动 timeout"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-to-001", assignee="agent-c")
        t.update_status("task-to-001", "running")
        # create() 会挂 pipeline chain；有活跃 running step 时故意跳过 timeout
        task = t.get("task-to-001")
        task["chain"] = []
        from lib.infra.utils import json_write
        json_write(t._task_path("task-to-001"), task)
        t.increment_reminder("task-to-001")
        t.increment_reminder("task-to-001")
        t.increment_reminder("task-to-001")
        t.increment_reminder("task-to-001")  # 已超过 max_reminders=3
        agents = {"agent-c": {"name": "agent-c"}}
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
        t.update_status("task-la-001", "success")
        t.update_status("task-la-002", "running")
        all_tasks = t.list_all()
        assert len(all_tasks) == 2
        running = t.list_all(status_filter="running")
        assert len(running) == 1
    print("  ✓ test_list_all")


def test_list_all_ordering():
    """验证倒序排序正确性：最新的 updated_at 应排在最前面"""
    import json
    from lib.infra.utils import json_write
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        tasks_dir = os.path.join(td, "tasks")
        os.makedirs(tasks_dir, exist_ok=True)

        # 直接写入带不同 updated_at 的任务（模拟时间间隔）
        task_old = {
            "task_id": "task-order-001", "summary": "最早",
            "status": "success",
            "updated_at": "2026-06-03T10:00:00+0800",
        }
        task_mid = {
            "task_id": "task-order-002", "summary": "中间",
            "status": "running",
            "updated_at": "2026-06-03T12:00:00+0800",
        }
        task_new = {
            "task_id": "task-order-003", "summary": "最新",
            "status": "running",
            "updated_at": "2026-06-03T15:00:00+0800",
        }
        json_write(os.path.join(tasks_dir, "task-order-001.json"), task_old)
        json_write(os.path.join(tasks_dir, "task-order-002.json"), task_mid)
        json_write(os.path.join(tasks_dir, "task-order-003.json"), task_new)

        all_tasks = t.list_all()
        assert len(all_tasks) == 3
        # 最新更新的在最上面
        assert all_tasks[0]["task_id"] == "task-order-003", \
            f"预期 task-order-003 排最前，实际: {all_tasks[0]['task_id']}"
        assert all_tasks[1]["task_id"] == "task-order-002"
        assert all_tasks[2]["task_id"] == "task-order-001"
    print("  ✓ test_list_all_ordering")


def test_list_all_ordering_with_timezone():
    """验证带 +0800 时区后缀的 updated_at 排序正确"""
    import json
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        # 直接写入带不同时区的 updated_at（模拟真实场景）
        tasks_dir = os.path.join(td, "tasks")
        os.makedirs(tasks_dir, exist_ok=True)

        # 注意：+0800 的时间比 +0000 的时间「看起来」小时更大
        # 但实际 UTC 时间 +0800 的更早
        task_a = {
            "task_id": "task-tz-001",
            "summary": "有+0800的较晚记录",
            "status": "pending",
            "updated_at": "2026-06-03T15:12:58+0800",  # UTC 07:12:58
        }
        task_b = {
            "task_id": "task-tz-002",
            "summary": "有+0000的较早记录",
            "status": "pending",
            "updated_at": "2026-06-03T10:12:58+0000",  # UTC 10:12:58 → 实际更晚
        }
        # 用 json_write 写入
        from lib.infra.utils import json_write
        json_write(os.path.join(tasks_dir, "task-tz-001.json"), task_a)
        json_write(os.path.join(tasks_dir, "task-tz-002.json"), task_b)

        all_tasks = t.list_all()
        assert len(all_tasks) == 2
        # task-tz-002 的 UTC 时间更晚（10:12:58 > 07:12:58），应排前面
        assert all_tasks[0]["task_id"] == "task-tz-002", \
            f"预期 task-tz-002 排最前（UTC 10:12:58），实际: {all_tasks[0]['task_id']}"
        assert all_tasks[1]["task_id"] == "task-tz-001"
    print("  ✓ test_list_all_ordering_with_timezone")


def test_add_audit_with_new_fields():
    """测试增强的审计记录（含 category/severity/affected_components）"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-audit-new-001", summary="代码审查测试", assignee="agent-g")
        t.update_status("task-audit-new-001", "success")

        task = t.add_audit(
            task_id="task-audit-new-001",
            reviewer="agent-e",
            result="pass",
            issues=[{"desc": "代码风格良好", "severity": "low", "file": "lib/tracker.py"}],
            summary="首次审查通过",
            category="code_review",
            severity="high",
            affected_components=["lib/tracker.py", "lib/api/handlers_tasks.py"],
        )
        assert task is not None
        assert len(task["audit_log"]) == 1
        entry = task["audit_log"][0]
        assert entry["reviewer"] == "agent-e"
        assert entry["result"] == "pass"
        assert entry["category"] == "code_review"
        assert entry["severity"] == "high"
        assert entry["round"] == 1
        assert "lib/tracker.py" in entry["affected_components"]
        assert len(entry["issues"]) == 1
        assert entry["issues"][0]["desc"] == "代码风格良好"
    print("  ✓ test_add_audit_with_new_fields")


def test_audit_stats():
    """测试审计聚合统计"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)

        # 创建任务并添加审计记录
        for i in range(5):
            tid = f"task-stats-{i:03d}"
            t.create(tid, summary=f"测试任务{i}", assignee="agent-g")
            t.update_status(tid, "success")

        # 给其中 3 个任务加审计
        t.add_audit("task-stats-000", "agent-e", "pass", category="code_review")
        t.add_audit("task-stats-001", "agent-e", "pass", category="code_review")
        t.add_audit("task-stats-002", "agent-f", "fail", category="security",
                     severity="critical", issues=[{"desc": "安全漏洞"}])

        stats = t.audit_stats()
        assert stats["total_tasks"] == 5
        assert stats["audited_tasks"] == 3
        assert stats["pending_audit_tasks"] == 2  # 2 个 success 但无审计
        assert stats["pass_count"] == 2
        assert stats["fail_count"] == 1
        assert stats["warn_count"] == 0
        assert stats["pass_rate"] == 66.7
        assert stats["total_audit_entries"] == 3
        assert stats["by_reviewer"]["agent-e"]["total"] == 2
        assert stats["by_reviewer"]["agent-f"]["total"] == 1
        assert stats["by_category"]["code_review"] == 2
        assert stats["by_category"]["security"] == 1
        assert stats["by_severity"]["critical"] == 1
        assert len(stats["latest_audits"]) == 3
    print("  ✓ test_audit_stats")


def test_list_pending_audit():
    """测试列出待审计任务"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)

        t.create("task-pend-001", summary="已完成未审计", assignee="agent-g")
        t.update_status("task-pend-001", "success")

        t.create("task-pend-002", summary="进行中无需审计", assignee="agent-g")
        t.update_status("task-pend-002", "running")

        t.create("task-pend-003", summary="已审计任务", assignee="agent-g")
        t.update_status("task-pend-003", "success")
        t.add_audit("task-pend-003", "agent-e", "pass")

        pending = t.list_pending_audit()
        assert len(pending) == 1
        assert pending[0]["task_id"] == "task-pend-001"
    print("  ✓ test_list_pending_audit")


def test_audit_trend_day():
    """测试审计趋势（按日聚合）"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-trend-day-001", summary="日趋势测试-1")
        t.update_status("task-trend-day-001", "success")
        # 写入模拟的审计记录（不同日期）
        from lib.infra.utils import json_write
        tasks_dir = os.path.join(td, "tasks")
        task_path = os.path.join(tasks_dir, "task-trend-day-001.json")
        task_data = json_read(task_path, {})
        task_data["audit_log"] = [
            {"reviewer": "agent-e", "result": "pass", "at": "2026-06-01T10:00:00+0800", "category": "code_review"},
            {"reviewer": "agent-f", "result": "pass", "at": "2026-06-01T11:00:00+0800", "category": "security"},
            {"reviewer": "agent-e", "result": "fail", "at": "2026-06-02T10:00:00+0800", "category": "code_review"},
            {"reviewer": "agent-f", "result": "warn", "at": "2026-06-03T10:00:00+0800", "category": "performance"},
        ]
        json_write(task_path, task_data)

        result = t.audit_trend(period="day")
        assert len(result["trend"]) == 3
        # 2026-06-01: 2 pass
        assert result["trend"][0]["period"] == "2026-06-01"
        assert result["trend"][0]["total"] == 2
        assert result["trend"][0]["pass"] == 2
        # 2026-06-02: 1 fail
        assert result["trend"][1]["period"] == "2026-06-02"
        assert result["trend"][1]["fail"] == 1
        # 2026-06-03: 1 warn
        assert result["trend"][2]["period"] == "2026-06-03"
        assert result["trend"][2]["warn"] == 1
        # summary
        assert result["summary"]["total_audits"] == 4
        assert result["summary"]["avg_pass_rate"] == 50.0
        assert result["summary"]["period"] == "day"
    print("  ✓ test_audit_trend_day")


def test_audit_trend_week():
    """测试审计趋势（按周聚合）"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-trend-week-001", summary="周趋势测试")
        t.update_status("task-trend-week-001", "success")
        from lib.infra.utils import json_write
        tasks_dir = os.path.join(td, "tasks")
        task_path = os.path.join(tasks_dir, "task-trend-week-001.json")
        task_data = json_read(task_path, {})
        task_data["audit_log"] = [
            {"reviewer": "agent-e", "result": "pass", "at": "2026-06-01T10:00:00+0800"},  # W23
            {"reviewer": "agent-e", "result": "pass", "at": "2026-06-02T10:00:00+0800"},  # W23
            {"reviewer": "agent-f", "result": "fail", "at": "2026-06-08T10:00:00+0800"},    # W24
        ]
        json_write(task_path, task_data)

        result = t.audit_trend(period="week")
        assert len(result["trend"]) == 2
        # W23 有2条审计记录
        assert "W23" in result["trend"][0]["period"]
        assert result["trend"][0]["total"] == 2
        # W24 有1条
        assert "W24" in result["trend"][1]["period"]
        assert result["trend"][1]["total"] == 1
        assert result["summary"]["total_audits"] == 3
    print("  ✓ test_audit_trend_week")


def test_audit_trend_month():
    """测试审计趋势（按月聚合）"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        t.create("task-trend-month-001", summary="月趋势测试")
        t.update_status("task-trend-month-001", "success")
        from lib.infra.utils import json_write
        tasks_dir = os.path.join(td, "tasks")
        task_path = os.path.join(tasks_dir, "task-trend-month-001.json")
        task_data = json_read(task_path, {})
        task_data["audit_log"] = [
            {"reviewer": "agent-e", "result": "pass", "at": "2026-06-01T10:00:00+0800"},
            {"reviewer": "agent-f", "result": "fail", "at": "2026-06-15T10:00:00+0800"},
            {"reviewer": "agent-f", "result": "pass", "at": "2026-07-01T10:00:00+0800"},
        ]
        json_write(task_path, task_data)

        result = t.audit_trend(period="month")
        assert len(result["trend"]) == 2
        assert result["trend"][0]["period"] == "2026-06"
        assert result["trend"][0]["total"] == 2
        assert result["trend"][0]["pass"] == 1
        assert result["trend"][0]["fail"] == 1
        assert result["trend"][1]["period"] == "2026-07"
        assert result["trend"][1]["total"] == 1
        assert result["summary"]["total_audits"] == 3
        assert result["summary"]["period"] == "month"
    print("  ✓ test_audit_trend_month")


def test_audit_trend_empty():
    """测试无审计记录时的趋势返回"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)
        result = t.audit_trend()
        assert result["trend"] == []
        assert result["summary"]["total_audits"] == 0
        assert result["summary"]["avg_pass_rate"] == 0.0
    print("  ✓ test_audit_trend_empty")


def test_truncate_to_period():
    """测试 _truncate_to_period 工具方法"""
    assert TaskTracker._truncate_to_period("2026-06-03T15:12:58+0800", "day") == "2026-06-03"
    assert TaskTracker._truncate_to_period("2026-06-03T15:12:58", "day") == "2026-06-03"
    assert TaskTracker._truncate_to_period("2026-06-01T10:00:00", "week").endswith("W23")
    assert TaskTracker._truncate_to_period("2026-06-01T10:00:00", "month") == "2026-06"
    assert TaskTracker._truncate_to_period("", "day") == ""
    assert TaskTracker._truncate_to_period(None, "day") == ""
    print("  ✓ test_truncate_to_period")


def test_list_by_filters():
    """测试多条件过滤任务列表"""
    with tempfile.TemporaryDirectory() as td:
        t = TaskTracker(td)

        t.create("task-flt-001", summary="任务A", assignee="agent-g")
        t.update_status("task-flt-001", "success")
        t.add_audit("task-flt-001", "agent-e", "pass")

        t.create("task-flt-002", summary="任务B", assignee="agent-i")
        t.update_status("task-flt-002", "running")

        t.create("task-flt-003", summary="任务C", assignee="agent-g")
        t.update_status("task-flt-003", "success")

        # 按状态过滤
        result = t.list_by_filters(status="success")
        assert result["total"] == 2

        # 按负责人过滤
        result = t.list_by_filters(assignee="agent-i")
        assert result["total"] == 1
        assert result["tasks"][0]["task_id"] == "task-flt-002"

        # 按审计状态过滤
        result = t.list_by_filters(audit_status="audited")
        assert result["total"] == 1
        assert result["tasks"][0]["task_id"] == "task-flt-001"

        result = t.list_by_filters(audit_status="pending-audit")
        assert result["total"] == 1
        assert result["tasks"][0]["task_id"] == "task-flt-003"

        # 按审查人过滤
        result = t.list_by_filters(reviewer="agent-e")
        assert result["total"] == 1
        assert result["tasks"][0]["task_id"] == "task-flt-001"

        # 分页测试
        result = t.list_by_filters(limit=1, offset=0)
        assert len(result["tasks"]) == 1
        assert result["total"] == 3
    print("  ✓ test_list_by_filters")


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
    test_list_all_ordering()
    test_list_all_ordering_with_timezone()
    test_add_audit_with_new_fields()
    test_audit_stats()
    test_list_pending_audit()
    test_list_by_filters()
    test_audit_trend_day()
    test_audit_trend_week()
    test_audit_trend_month()
    test_audit_trend_empty()
    test_truncate_to_period()
    print("\n✓ 全部 21 个测试通过")
