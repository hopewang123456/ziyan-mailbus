"""P0 回归：pipeline_trigger 防误完成 / 跨步消费 / 精确结果文件匹配。"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.pipeline_trigger import (
    _find_result,
    _result_applies_to_step,
    trigger,
)
from lib.tracker import TaskTracker
from lib.utils import json_write, _now_iso


def _write_result(data_dir, task_id, payload):
    d = os.path.join(data_dir, "msg-results")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{task_id}.json")
    json_write(path, payload)
    return path


def _make_pipeline_task(data_dir, task_id, to_person="dali", to_role="开发工程师", step=1):
    started = _now_iso()
    chain = [{
        "step": step,
        "from_role": "调度员",
        "from_person": "xiaoqi",
        "to_role": to_role,
        "to_person": to_person,
        "action": "等待处理",
        "status": "running",
        "started_at": started,
        "completed_at": None,
        "report": None,
        "result_consumed": False,
    }]
    task = {
        "task_id": task_id,
        "summary": "P0 test",
        "assignee": to_person,
        "status": "running",
        "chain": chain,
        "requires_audit": False,
        "created_at": started,
        "updated_at": started,
    }
    tra = TaskTracker(data_dir)
    json_write(tra._task_path(task_id), task)
    return task, chain, started


def test_find_result_exact_only():
    with tempfile.TemporaryDirectory() as td:
        other = os.path.join(td, "msg-results", "other-task.json")
        os.makedirs(os.path.dirname(other), exist_ok=True)
        json_write(other, {"conclusion": "done"})
        assert _find_result(td, "target-task") is None
        exact = _write_result(td, "target-task", {"conclusion": "done"})
        assert _find_result(td, "target-task") == exact
    print("  ok test_find_result_exact_only")


def test_reject_wrong_pipeline_step():
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-step-mismatch"
        task, chain, started = _make_pipeline_task(td, task_id)
        current = chain[-1]
        path = _write_result(td, task_id, {
            "conclusion": "done",
            "pipeline_step": 99,
            "timestamp": started,
            "agent": "dali",
        })
        assert not _result_applies_to_step(
            json.load(open(path, encoding="utf-8")),
            path, task_id, current, chain,
        )
    print("  ok test_reject_wrong_pipeline_step")


def test_reject_stale_timestamp():
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-stale-ts"
        task, chain, started = _make_pipeline_task(td, task_id)
        current = chain[-1]
        path = _write_result(td, task_id, {
            "conclusion": "done",
            "pipeline_step": 1,
            "timestamp": "2020-01-01T00:00:00+00:00",
            "agent": "dali",
        })
        assert not _result_applies_to_step(
            json.load(open(path, encoding="utf-8")),
            path, task_id, current, chain,
        )
    print("  ok test_reject_stale_timestamp")


def test_result_consumed_skips_advance():
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-consumed"
        task, chain, started = _make_pipeline_task(td, task_id)
        current = chain[-1]
        current["result_consumed"] = True
        tra = TaskTracker(td)
        json_write(tra._task_path(task_id), task)
        _write_result(td, task_id, {
            "conclusion": "done",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "dali",
        })
        paths = {"inbox": os.path.join(td, "inbox")}
        os.makedirs(os.path.join(paths["inbox"], "lingjian"), exist_ok=True)
        json_write(os.path.join(paths["inbox"], "lingjian", "inbox.json"), {"agent": "lingjian", "messages": []})
        trigger(td, {"dali": {"name": "dali"}}, paths)
        after = tra.get(task_id)
        assert len(after["chain"]) == 1
        assert after["chain"][0].get("result_consumed") is True
    print("  ok test_result_consumed_skips_advance")


def test_valid_result_advances_chain():
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-advance"
        task, chain, started = _make_pipeline_task(td, task_id)
        _write_result(td, task_id, {
            "conclusion": "done",
            "summary": "step1 ok",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "dali",
            "task_id": task_id,
        })
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("lingjian", "dali", "yige"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {"dali": {"name": "dali"}, "lingjian": {"name": "lingjian"}}, paths)
        after = TaskTracker(td).get(task_id)
        assert len(after["chain"]) >= 2
        assert after["chain"][0].get("result_consumed") is True
        assert after["chain"][0]["status"] in ("completed", "done")
    print("  ok test_valid_result_advances_chain")


def test_same_next_role_uses_role_flow():
    """显式 next_role 与当前角色相同时不应卡住，应走 role_flow 表。"""
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-same-next"
        task, chain, started = _make_pipeline_task(td, task_id, to_role="开发工程师")
        _write_result(td, task_id, {
            "conclusion": "done",
            "next_role": "开发工程师",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "dali",
        })
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("lingjian", "dali"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {"dali": {"name": "dali"}, "lingjian": {"name": "lingjian"}}, paths)
        after = TaskTracker(td).get(task_id)
        assert len(after["chain"]) >= 2
        assert after["chain"][-1]["to_role"] != "开发工程师"
    print("  ok test_same_next_role_uses_role_flow")


def test_reject_wrong_agent():
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-wrong-agent"
        task, chain, started = _make_pipeline_task(td, task_id, to_person="dali")
        current = chain[-1]
        path = _write_result(td, task_id, {
            "conclusion": "done",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "xiaoqi",
        })
        assert not _result_applies_to_step(
            json.load(open(path, encoding="utf-8")),
            path, task_id, current, chain,
        )
    print("  ok test_reject_wrong_agent")


def test_reject_untrusted_mailbus_agent():
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-fake-mailbus"
        task, chain, started = _make_pipeline_task(td, task_id)
        current = chain[-1]
        path = _write_result(td, task_id, {
            "conclusion": "done",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "mailbus",
            "task_id": task_id,
        })
        assert not _result_applies_to_step(
            json.load(open(path, encoding="utf-8")),
            path, task_id, current, chain,
        )
    print("  ok test_reject_untrusted_mailbus_agent")


def test_reject_auto_linked_result():
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-auto-link"
        task, chain, started = _make_pipeline_task(td, task_id)
        current = chain[-1]
        path = _write_result(td, task_id, {
            "conclusion": "done",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "dali",
            "task_id": task_id,
            "source": "auto-linked-from-mailbus-scheduler-validation-20260616",
        })
        assert not _result_applies_to_step(
            json.load(open(path, encoding="utf-8")),
            path, task_id, current, chain,
        )
    print("  ok test_reject_auto_linked_result")


def test_planned_overrides_next_role():
    """有 planned 时 next_role=调度员 仍应 pop 出 lingxi，而非跳步到 xiaoqi。"""
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-planned-first"
        tra = TaskTracker(td)
        task = tra.create(
            task_id, "planned priority", assignee="lingzhao",
            chain_hops=["lingzhao", "lingxi", "xiaoqi", "lingjian"],
        )
        started = task["chain"][0]["started_at"]
        _write_result(td, task_id, {
            "conclusion": "done",
            "next_role": "调度员",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "lingzhao",
            "task_id": task_id,
        })
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("lingxi", "lingzhao", "xiaoqi", "lingjian"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {a: {} for a in ("lingxi", "lingzhao", "xiaoqi", "lingjian")}, paths)
        after = tra.get(task_id)
        assert after["chain"][-1]["to_person"] == "lingxi"
        assert after["chain"][-1]["to_role"] == "技术研究员"
    print("  ok test_planned_overrides_next_role")


def test_no_false_success_with_planned():
    """调度员 done 但 planned 未清空 → 不得 success。"""
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-no-false-success"
        tra = TaskTracker(td)
        task = tra.create(
            task_id, "no false success", assignee="lingzhao",
            chain_hops=["lingzhao", "lingxi", "xiaoqi"],
        )
        chain = task["chain"]
        chain[0]["status"] = "completed"
        chain[0]["result_consumed"] = True
        chain.append({
            "step": 2,
            "from_role": "方案设计师",
            "from_person": "lingzhao",
            "to_role": "调度员",
            "to_person": "xiaoqi",
            "status": "running",
            "started_at": _now_iso(),
            "result_consumed": False,
        })
        json_write(tra._task_path(task_id), task)
        started = chain[-1]["started_at"]
        _write_result(td, task_id, {
            "conclusion": "done",
            "pipeline_step": 2,
            "timestamp": started,
            "agent": "xiaoqi",
            "task_id": task_id,
        })
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("lingxi", "xiaoqi", "lingzhao"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {a: {} for a in ("lingxi", "xiaoqi", "lingzhao")}, paths)
        after = tra.get(task_id)
        assert after["status"] != "success"
        assert len(after["chain"]) >= 3
    print("  ok test_no_false_success_with_planned")


def test_planned_agents_routes_dali_after_lingxiao():
    """显式 chain [lingxiao,dali,lingjian]：灵霄完成后应派给大力而非再次灵霄/默认审查官。"""
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-planned-dali"
        tra = TaskTracker(td)
        task = tra.create(
            task_id, "planned agents test", assignee="lingxiao",
            chain_hops=["lingxiao", "dali", "lingjian"],
        )
        started = task["chain"][0]["started_at"]
        _write_result(td, task_id, {
            "conclusion": "done",
            "summary": "engine done",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "lingxiao",
        })
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("lingxiao", "dali", "lingjian"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {"lingxiao": {}, "dali": {}, "lingjian": {}}, paths)
        after = tra.get(task_id)
        assert len(after["chain"]) >= 2
        assert after["chain"][-1]["to_person"] == "dali"
        assert after["chain"][-1]["to_role"] == "开发工程师"
        assert after["chain"][0].get("planned_agents") == ["lingjian"]
    print("  ok test_planned_agents_routes_dali_after_lingxiao")


def test_next_person_override():
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-next-person"
        task, chain, started = _make_pipeline_task(td, task_id, to_person="lingxiao", to_role="开发工程师")
        _write_result(td, task_id, {
            "conclusion": "done",
            "next_person": "dali",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "lingxiao",
        })
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("dali", "lingxiao", "lingjian"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {"lingxiao": {}, "dali": {}, "lingjian": {}}, paths)
        after = TaskTracker(td).get(task_id)
        assert after["chain"][-1]["to_person"] == "dali"
    print("  ok test_next_person_override")


def test_need_research_advances_to_planned():
    """conclusion=need_research 应触发 planned 下一步（灵犀）。"""
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-need-research"
        tra = TaskTracker(td)
        task = tra.create(
            task_id, "need research", assignee="lingzhao",
            chain_hops=["lingzhao", "lingxi", "xiaoqi"],
        )
        started = task["chain"][0]["started_at"]
        _write_result(td, task_id, {
            "conclusion": "need_research",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "lingzhao",
            "task_id": task_id,
        })
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("lingxi", "lingzhao", "xiaoqi"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {a: {} for a in ("lingxi", "lingzhao", "xiaoqi")}, paths)
        after = tra.get(task_id)
        assert len(after["chain"]) >= 2
        assert after["chain"][-1]["to_person"] == "lingxi"
    print("  ok test_need_research_advances_to_planned")


def test_planned_skips_duplicate_person():
    from lib.pipeline_routing import resolve_next_assignee

    chain = [{
        "step": 1, "to_person": "xiaoqi", "status": "completed",
        "planned_agents": ["xiaoqi", "lingxiao"],
    }]
    result = {"conclusion": "dispatched", "summary": "ok"}
    role, person = resolve_next_assignee(chain, result, "调度员", "dispatched", {})
    assert person == "lingxiao", f"got {person}"
    assert chain[0]["planned_agents"] == []
    print("  ok test_planned_skips_duplicate_person")


if __name__ == "__main__":
    test_find_result_exact_only()
    test_reject_wrong_pipeline_step()
    test_reject_stale_timestamp()
    test_reject_wrong_agent()
    test_reject_untrusted_mailbus_agent()
    test_reject_auto_linked_result()
    test_planned_overrides_next_role()
    test_no_false_success_with_planned()
    test_need_research_advances_to_planned()
    test_result_consumed_skips_advance()
    test_valid_result_advances_chain()
    test_same_next_role_uses_role_flow()
    test_planned_agents_routes_dali_after_lingxiao()
    test_next_person_override()
    test_planned_skips_duplicate_person()
    print("\n  all P0 pipeline_trigger tests passed")
