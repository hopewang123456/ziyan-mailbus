"""P0 回归：pipeline_trigger 防误完成 / 跨步消费 / 精确结果文件匹配。"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.application.orchestration.pipeline.results import step_result_path
from lib.application.orchestration.pipeline.trigger import trigger
from lib.adapters.orchestration.task_fsm import result_applies_to_step, result_mtime_ok
from lib.application.orchestration.tracker import TaskTracker
from lib.infra.utils import json_write, _now_iso


def _result_applies_with_file(result, result_file, task_id, current, chain):
    """测试辅助：含 mtime 的 result_applies_to_step。"""
    mtime_ok = True
    step_started = current.get("started_at") or ""
    result_ts = result.get("timestamp") or result.get("updated_at") or ""
    if step_started and result_ts:
        from lib.application.orchestration.tracker import _parse_iso_dt
        try:
            mtime_ok = _parse_iso_dt(result_ts) >= _parse_iso_dt(step_started)
        except Exception:
            mtime_ok = True
    elif step_started and result_file and os.path.isfile(result_file):
        from datetime import datetime, timezone
        from lib.application.orchestration.tracker import _parse_iso_dt
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(result_file), tz=timezone.utc)
            mtime_ok = mtime >= _parse_iso_dt(step_started)
        except (OSError, Exception):
            pass
    ok, _ = result_applies_to_step(
        result, task_id, current, chain, result_mtime_ok=mtime_ok,
    )
    return ok


def _write_result(data_dir, task_id, payload, step_id="s1"):
    path = step_result_path(data_dir, task_id, step_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = dict(payload)
    body.setdefault("step_id", step_id)
    json_write(path, body)
    return path


# 测试专用 role-types（自包含，不依赖本机团队包/真实人名）
_TEST_ROLE_TYPES = {
    "version": "1.0.0",
    "_note": "pytest fixture: generic agent ids for self-contained pipeline tests",
    "roles": {
        "1": {"display": {"zh": "方案设计师"}, "candidates": ["agent-a"]},
        "3": {"display": {"zh": "技术研究员"}, "candidates": ["agent-b"]},
        "9": {"display": {"zh": "调度员"}, "candidates": ["agent-c"]},
        "5": {"display": {"zh": "审查官"}, "candidates": ["agent-d"]},
        "8": {"display": {"zh": "开发工程师"}, "candidates": ["agent-e"]},
        "6": {"display": {"zh": "测试工程师"}, "candidates": ["agent-f"]},
        "12": {"display": {"zh": "验收员"}, "candidates": ["agent-g"]},
    },
}


def _write_role_types(data_dir):
    """写入自包含 role-types.json，保证角色解析不读本机团队包。"""
    p = os.path.join(data_dir, "roles", "json", "role-types.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json_write(p, _TEST_ROLE_TYPES)


def _make_pipeline_task(data_dir, task_id, to_person="agent-e", to_role="开发工程师", step=1):
    started = _now_iso()
    chain = [{
        "step": step,
        "step_id": "s1",
        "from_role": "调度员",
        "from_person": "agent-c",
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


def test_find_result_step_path_only():
    with tempfile.TemporaryDirectory() as td:
        other = os.path.join(td, "msg-results", "other-task", "step-s1.json")
        os.makedirs(os.path.dirname(other), exist_ok=True)
        json_write(other, {"conclusion": "done"})
        missing = step_result_path(td, "target-task", "s1")
        assert not os.path.isfile(missing)
        exact = _write_result(td, "target-task", {"conclusion": "done"})
        assert exact == step_result_path(td, "target-task", "s1")
        assert os.path.isfile(exact)
    print("  ok test_find_result_step_path_only")


def test_reject_wrong_pipeline_step():
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-step-mismatch"
        task, chain, started = _make_pipeline_task(td, task_id)
        current = chain[-1]
        path = _write_result(td, task_id, {
            "conclusion": "done",
            "pipeline_step": 99,
            "timestamp": started,
            "agent": "agent-e",
        })
        assert not _result_applies_with_file(
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
            "agent": "agent-e",
        })
        assert not _result_applies_with_file(
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
            "agent": "agent-e",
        })
        _write_role_types(td)
        paths = {"inbox": os.path.join(td, "inbox")}
        os.makedirs(os.path.join(paths["inbox"], "agent-d"), exist_ok=True)
        json_write(os.path.join(paths["inbox"], "agent-d", "inbox.json"), {"agent": "agent-d", "messages": []})
        trigger(td, {"agent-e": {"name": "agent-e"}}, paths)
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
            "agent": "agent-e",
            "task_id": task_id,
        })
        _write_role_types(td)
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("agent-d", "agent-e", "agent-g"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {"agent-e": {"name": "agent-e"}, "agent-d": {"name": "agent-d"}}, paths)
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
            "agent": "agent-e",
        })
        _write_role_types(td)
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("agent-d", "agent-e"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {"agent-e": {"name": "agent-e"}, "agent-d": {"name": "agent-d"}}, paths)
        after = TaskTracker(td).get(task_id)
        assert len(after["chain"]) >= 2
        assert after["chain"][-1]["to_role"] != "开发工程师"
    print("  ok test_same_next_role_uses_role_flow")


def test_reject_wrong_agent():
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-wrong-agent"
        task, chain, started = _make_pipeline_task(td, task_id, to_person="agent-e")
        current = chain[-1]
        path = _write_result(td, task_id, {
            "conclusion": "done",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "agent-c",
        })
        assert not _result_applies_with_file(
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
        assert not _result_applies_with_file(
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
            "agent": "agent-e",
            "task_id": task_id,
            "source": "auto-linked-from-mailbus-scheduler-validation-20260616",
        })
        assert not _result_applies_with_file(
            json.load(open(path, encoding="utf-8")),
            path, task_id, current, chain,
        )
    print("  ok test_reject_auto_linked_result")


def test_planned_overrides_next_role():
    """有 planned 时 next_role=调度员 仍应 pop 出 agent-b，而非跳步到 agent-c。"""
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-planned-first"
        tra = TaskTracker(td)
        task = tra.create(
            task_id, "planned priority", assignee="agent-a",
            chain_hops=["agent-a", "agent-b", "agent-c", "agent-d"],
        )
        started = task["chain"][0]["started_at"]
        _write_result(td, task_id, {
            "conclusion": "done",
            "next_role": "调度员",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "agent-a",
            "task_id": task_id,
        })
        _write_role_types(td)
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("agent-b", "agent-a", "agent-c", "agent-d"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {a: {} for a in ("agent-b", "agent-a", "agent-c", "agent-d")}, paths)
        after = tra.get(task_id)
        assert after["chain"][-1]["to_person"] == "agent-b"
        assert after["chain"][-1]["to_role"] == "技术研究员"
    print("  ok test_planned_overrides_next_role")


def test_no_false_success_with_planned():
    """调度员 done 但 planned 未清空 → 不得 success。"""
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-no-false-success"
        tra = TaskTracker(td)
        task = tra.create(
            task_id, "no false success", assignee="agent-a",
            chain_hops=["agent-a", "agent-b", "agent-c"],
        )
        chain = task["chain"]
        chain[0]["status"] = "completed"
        chain[0]["result_consumed"] = True
        chain.append({
            "step": 2,
            "from_role": "方案设计师",
            "from_person": "agent-a",
            "to_role": "调度员",
            "to_person": "agent-c",
            "status": "running",
            "started_at": _now_iso(),
            "result_consumed": False,
        })
        json_write(tra._task_path(task_id), task)
        started = chain[-1]["started_at"]
        sid = chain[-1].get("step_id") or "s2"
        chain[-1]["step_id"] = sid
        json_write(tra._task_path(task_id), task)
        _write_result(td, task_id, {
            "conclusion": "done",
            "pipeline_step": 2,
            "timestamp": started,
            "agent": "agent-c",
            "task_id": task_id,
        }, step_id=sid)
        _write_role_types(td)
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("agent-b", "agent-c", "agent-a"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {a: {} for a in ("agent-b", "agent-c", "agent-a")}, paths)
        after = tra.get(task_id)
        assert after["status"] != "success"
        assert len(after["chain"]) >= 3
    print("  ok test_no_false_success_with_planned")


def test_planned_agents_routes_next_after_first():
    """显式 chain [agent-f,agent-e,agent-d]：首个执行人完成后应派给第二个，而非跳步到默认审查官。"""
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-planned-agent-e"
        tra = TaskTracker(td)
        task = tra.create(
            task_id, "planned agents test", assignee="agent-f",
            chain_hops=["agent-f", "agent-e", "agent-d"],
        )
        started = task["chain"][0]["started_at"]
        _write_result(td, task_id, {
            "conclusion": "done",
            "summary": "engine done",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "agent-f",
        })
        _write_role_types(td)
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("agent-f", "agent-e", "agent-d"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {"agent-f": {}, "agent-e": {}, "agent-d": {}}, paths)
        after = tra.get(task_id)
        assert len(after["chain"]) >= 2
        assert after["chain"][-1]["to_person"] == "agent-e"
        assert after["chain"][-1]["to_role"] == "开发工程师"
        assert after["chain"][0].get("planned_agents") == ["agent-d"]
    print("  ok test_planned_agents_routes_next_after_first")


def test_next_person_override():
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-next-person"
        task, chain, started = _make_pipeline_task(td, task_id, to_person="agent-f", to_role="开发工程师")
        _write_result(td, task_id, {
            "conclusion": "done",
            "next_person": "agent-e",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "agent-f",
        })
        _write_role_types(td)
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("agent-e", "agent-f", "agent-d"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {"agent-f": {}, "agent-e": {}, "agent-d": {}}, paths)
        after = TaskTracker(td).get(task_id)
        assert after["chain"][-1]["to_person"] == "agent-e"
    print("  ok test_next_person_override")


def test_need_research_advances_to_planned():
    """conclusion=need_research 应触发 planned 下一步（技术研究员）。"""
    with tempfile.TemporaryDirectory() as td:
        task_id = "p0-need-research"
        tra = TaskTracker(td)
        task = tra.create(
            task_id, "need research", assignee="agent-a",
            chain_hops=["agent-a", "agent-b", "agent-c"],
        )
        started = task["chain"][0]["started_at"]
        _write_result(td, task_id, {
            "conclusion": "need_research",
            "pipeline_step": 1,
            "timestamp": started,
            "agent": "agent-a",
            "task_id": task_id,
        })
        _write_role_types(td)
        paths = {"inbox": os.path.join(td, "inbox")}
        for agent in ("agent-b", "agent-a", "agent-c"):
            os.makedirs(os.path.join(paths["inbox"], agent), exist_ok=True)
            json_write(
                os.path.join(paths["inbox"], agent, "inbox.json"),
                {"agent": agent, "messages": [], "has_unread": False},
            )
        trigger(td, {a: {} for a in ("agent-b", "agent-a", "agent-c")}, paths)
        after = tra.get(task_id)
        assert len(after["chain"]) >= 2
        assert after["chain"][-1]["to_person"] == "agent-b"
    print("  ok test_need_research_advances_to_planned")


def test_planned_skips_duplicate_person():
    from lib.application.orchestration.pipeline.routing import resolve_next_assignee

    chain = [{
        "step": 1, "to_person": "agent-c", "status": "completed",
        "planned_agents": ["agent-c", "agent-f"],
    }]
    result = {"conclusion": "dispatched", "summary": "ok"}
    role, person = resolve_next_assignee(chain, result, "调度员", "dispatched", {})
    assert person == "agent-f", f"got {person}"
    assert chain[0]["planned_agents"] == []
    print("  ok test_planned_skips_duplicate_person")


if __name__ == "__main__":
    test_find_result_step_path_only()
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
    test_planned_agents_routes_next_after_first()
    test_next_person_override()
    test_planned_skips_duplicate_person()
    print("\n  all P0 pipeline_trigger tests passed")
