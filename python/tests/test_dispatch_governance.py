"""治理增强：负载感知选人 · 工单事件时间线 · 管理者待办聚合。"""
import json
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, ROOT)


def _write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)


def _seed_basic(tmp):
    """最小可用 runtime：config agents + role-types + inbox 目录。"""
    _write(os.path.join(tmp, "config.json"), {
        "agents": {"a1": {"type": "codex"}, "a2": {"type": "hermes"}},
        "dispatch": {"load_aware": True, "default_concurrency": 1},
    })
    _write(os.path.join(tmp, "roles", "json", "role-types.json"), {
        "roles": {
            "8": {"key": "developer", "display": {"zh": "开发工程师", "en": "Developer"},
                  "candidates": ["a1", "a2"]}
        }
    })
    for a in ("a1", "a2"):
        _write(os.path.join(tmp, "inbox", a, "inbox.json"), {"agent": a, "messages": []})


def _busy_task(tmp, task_id, agent):
    _write(os.path.join(tmp, "tasks", f"{task_id}.json"), {
        "task_id": task_id, "status": "running", "assignee": agent,
        "chain": [{"step_id": "s1", "role_type": 8, "to_agent": agent,
                   "fsm_state": "dispatched", "status": "running"}],
        "updated_at": "2026-09-10T00:00:00+08:00",
    })


class TestLoadAwareDispatch(unittest.TestCase):
    def _resolve(self, tmp, **kw):
        from lib.application.orchestration.dispatch.role_resolver import resolve_agent_for_role_type
        return resolve_agent_for_role_type(tmp, 8, **kw)

    def test_idle_first_candidate_chosen(self):
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            _seed_basic(tmp)
            agent, meta = self._resolve(tmp)
            self.assertEqual(agent, "a1")
            self.assertEqual(meta["source"], "idle_first")

    def test_busy_first_gives_second(self):
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            _seed_basic(tmp)
            _busy_task(tmp, "t1", "a1")
            agent, meta = self._resolve(tmp)
            self.assertEqual(agent, "a2")
            self.assertEqual(meta["source"], "idle_first")
            self.assertEqual(meta["skipped_busy"], ["a1"])

    def test_all_busy_falls_back_round_robin(self):
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            _seed_basic(tmp)
            _busy_task(tmp, "t1", "a1")
            _busy_task(tmp, "t2", "a2")
            agent, meta = self._resolve(tmp)
            self.assertEqual(meta["source"], "round_robin")
            self.assertIn(agent, ("a1", "a2"))

    def test_concurrency_limit_respected(self):
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            _seed_basic(tmp)
            cfg = json.load(open(os.path.join(tmp, "config.json"), encoding="utf-8"))
            cfg["agents"]["a1"]["concurrency"] = 2
            json.dump(cfg, open(os.path.join(tmp, "config.json"), "w", encoding="utf-8"), ensure_ascii=False)
            _busy_task(tmp, "t1", "a1")  # 1 active < 2 → 未达上限
            agent, meta = self._resolve(tmp)
            self.assertEqual(agent, "a1")

    def test_pin_wins_over_busy(self):
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            _seed_basic(tmp)
            _busy_task(tmp, "t1", "a1")
            agent, meta = self._resolve(tmp, pin_agent="a1")
            self.assertEqual(agent, "a1")
            self.assertEqual(meta["source"], "pin")

    def test_load_aware_off_restores_round_robin(self):
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            _seed_basic(tmp)
            cfg = json.load(open(os.path.join(tmp, "config.json"), encoding="utf-8"))
            cfg["dispatch"]["load_aware"] = False
            json.dump(cfg, open(os.path.join(tmp, "config.json"), "w", encoding="utf-8"), ensure_ascii=False)
            _busy_task(tmp, "t1", "a1")
            agent, meta = self._resolve(tmp)
            self.assertEqual(meta["source"], "round_robin")


class TestTaskEvents(unittest.TestCase):
    def test_append_and_order(self):
        from lib.application.orchestration.tracker import append_task_event
        task = {"task_id": "t1"}
        append_task_event(task, "task_created", actor="human", note="需求")
        append_task_event(task, "fsm:rollback", actor="manager", note="返工", data={"to_step": "s1"})
        self.assertEqual(len(task["events"]), 2)
        self.assertEqual([e["action"] for e in task["events"]], ["task_created", "fsm:rollback"])
        self.assertEqual(task["events"][1]["actor"], "manager")
        self.assertEqual(task["events"][1]["data"]["to_step"], "s1")

    def test_cap_truncates_oldest(self):
        import lib.application.orchestration.tracker as tracker_mod
        old_cap = tracker_mod.MAX_TASK_EVENTS
        tracker_mod.MAX_TASK_EVENTS = 3
        try:
            task = {}
            for i in range(6):
                tracker_mod.append_task_event(task, f"e{i}", actor="system")
            self.assertEqual(len(task["events"]), 3)
            self.assertEqual(task["events"][0]["action"], "e3")
            self.assertEqual(task["events"][-1]["action"], "e5")
        finally:
            tracker_mod.MAX_TASK_EVENTS = old_cap

    def test_envelope_creation_records_task_created(self):
        from tests.test_helpers import seed_runtime_from_sot
        from lib.application.orchestration.tracker import TaskTracker
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            seed_runtime_from_sot(tmp)
            task = TaskTracker(tmp).create_from_envelope(
                {"task_id": "gov-ev-1", "mode": "explicit", "initiator": "manager-zh", "intent": "做个爬虫"},
                planned_chain=[{"role_type": 8, "reason": "test"}],
                plan_meta={"method": "rules", "confidence": 1.0},
            )
            self.assertEqual(task["events"][-1]["action"], "task_created")
            self.assertEqual(task["events"][-1]["actor"], "manager-zh")


class TestManagerQueries(unittest.TestCase):
    def _task(self, tid, fsm_state, substate=None, status="running", prio=50):
        return {
            "task_id": tid, "summary": tid, "status": status,
            "priority": prio, "updated_at": "2026-09-10T00:00:00+08:00",
            "fsm": {"state": fsm_state, "substate": substate, "priority": prio},
            "chain": [],
        }

    def test_bucket_aggregation(self):
        from lib.application.queries.manager import manager_pending
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            _write(os.path.join(tmp, "tasks", "p1.json"), self._task("p1", "created", "await_plan_approval", prio=10))
            _write(os.path.join(tmp, "tasks", "a1.json"), self._task("a1", "accepting", prio=50))
            _write(os.path.join(tmp, "tasks", "c1.json"), self._task("c1", "blocked", prio=80))
            _write(os.path.join(tmp, "tasks", "run1.json"), self._task("run1", "executing", prio=50))
            out = manager_pending(tmp)
            self.assertEqual(out["total"], 3)
            self.assertEqual(out["counts"], {"plan_approval": 1, "acceptance": 1, "coordination": 1})
            by_id = {it["task_id"]: it for it in out["items"]}
            self.assertEqual(by_id["p1"]["suggested_actions"], ["approve-plan", "rollback", "cancel", "priority"])
            self.assertIn("accept", by_id["a1"]["suggested_actions"])
            self.assertIn("continue", by_id["c1"]["suggested_actions"])


if __name__ == "__main__":
    unittest.main()


class _FakeHandler:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.status = 200
        self.payload = None

    def _send_json(self, payload, status=200):
        self.payload = payload
        self.status = status


def _bucket_task(tid, fsm_state, substate=None, status="running", prio=50):
    return {
        "task_id": tid, "summary": tid, "status": status,
        "updated_at": "2026-09-10T00:00:00+08:00",
        "fsm": {"state": fsm_state, "substate": substate, "priority": prio},
        "chain": [],
    }


class TestManagerPendingEndpoint(unittest.TestCase):
    def test_get_manager_pending_returns_buckets(self):
        from lib.api.handlers_tasks import handle_manager_pending
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            for tid, state, sub in (
                ("p1", "created", "await_plan_approval"),
                ("a1", "accepting", None),
                ("c1", "blocked", None),
            ):
                _write(os.path.join(tmp, "tasks", f"{tid}.json"), _bucket_task(tid, state, sub))
            h = _FakeHandler(tmp)
            handle_manager_pending(h)
            self.assertEqual(h.status, 200)
            self.assertEqual(h.payload["total"], 3)
            self.assertEqual(h.payload["counts"], {"plan_approval": 1, "acceptance": 1, "coordination": 1})


def _seed_flow_sot(tmp):
    _write(os.path.join(tmp, "roles", "json", "role-types.json"), {
        "roles": {
            str(k): {"key": f"k{k}", "display": {"zh": name, "en": name}, "candidates": [f"agent{k}"]}
            for k, name in ((1, "方案设计师"), (5, "审查官"), (6, "测试工程师"),
                            (8, "开发工程师"), (9, "调度员"), (12, "验收员"))
        }
    })
    _write(os.path.join(tmp, "roles", "json", "role-flow.json"), {
        "terminal": [{"role_type": 12, "conclusion": "approved"}],
        "blocked_fallback_role_type": 1,
        "transitions": [
            {"from_role_type": 8, "conclusion": "done", "to_role_type": 5},
            {"from_role_type": 8, "conclusion": "blocked", "to_role_type": 1},
            {"from_role_type": 5, "conclusion": "pass", "to_role_type": 6},
            {"from_role_type": 6, "conclusion": "pass", "to_role_type": 12},
        ],
    })


class TestFlowSoTUnification(unittest.TestCase):
    """P0-2：role-flow.json SoT 接入主路由，legacy 仅兜底。"""

    def test_next_after_uses_so_transition(self):
        from lib.application.orchestration.pipeline.routing import resolve_next_assignee
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            _seed_flow_sot(tmp)
            chain = [{"step_id": "s1", "role_type": 8, "to_person": "agent8"}]
            n_role, n_person = resolve_next_assignee(
                chain, {}, "开发工程师", "done", data_dir=tmp,
            )
            self.assertEqual(n_role, "审查官")
            self.assertEqual(n_person, "agent5")

    def test_blocked_uses_so_fallback(self):
        from lib.application.orchestration.pipeline.routing import resolve_next_assignee
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            _seed_flow_sot(tmp)
            chain = [{"step_id": "s1", "role_type": 9, "to_person": "agent9"}]
            n_role, _ = resolve_next_assignee(chain, {}, "调度员", "blocked", data_dir=tmp)
            self.assertEqual(n_role, "方案设计师")

    def test_terminal_from_so(self):
        from lib.application.orchestration.pipeline.routing import is_pipeline_terminal
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            _seed_flow_sot(tmp)
            chain = [{"step_id": "s1", "role_type": 12, "to_person": "agent12"}]
            self.assertTrue(is_pipeline_terminal(
                "验收员", "approved", chain, data_dir=tmp, current_role_type=12))
            self.assertFalse(is_pipeline_terminal(
                "开发工程师", "done", chain, data_dir=tmp, current_role_type=8))


class TestCollabPlanExpansion(unittest.TestCase):
    """P0-1 起步版：parallel_join 编排契约解析与展开。"""

    def _expand(self, chain, body=None):
        from lib.application.orchestration.dispatch.collab_plan import expand_planned_chain_for_collab
        return expand_planned_chain_for_collab(chain, body or {})

    def test_plain_items_pass_through(self):
        out = self._expand([{"role_type": 8, "reason": "r"}])
        self.assertEqual(out, [{"role_type": 8, "reason": "r"}])

    def test_parallel_join_expands_with_group_meta(self):
        out = self._expand([{
            "kind": "parallel_join",
            "parallel": [{"role_type": 8, "pin_agent": "a1"}, {"role_type": 5}],
            "join": {"role_type": 6, "gate": "review"},
        }])
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0]["parallel_group"], "g1")
        self.assertEqual(out[0]["collab_mode"], "parallel")
        self.assertEqual(out[0]["parallel_total"], 2)
        self.assertEqual(out[1]["parallel_group"], "g1")
        self.assertEqual(out[2]["collab_mode"], "join")
        self.assertEqual(out[2]["join_parallel_group"], "g1")
        self.assertEqual(out[2]["join_gate"], "review")
        self.assertEqual(out[2]["role_type"], 6)

    def test_invalid_gate_raises(self):
        from lib.application.orchestration.dispatch.collab_plan import CollabPlanError
        with self.assertRaises(CollabPlanError):
            self._expand([{
                "kind": "parallel_join",
                "parallel": [{"role_type": 8}, {"role_type": 5}],
                "join": {"role_type": 6, "gate": "auto-approve-all"},
            }])

    def test_less_than_two_parallel_raises(self):
        from lib.application.orchestration.dispatch.collab_plan import CollabPlanError
        with self.assertRaises(CollabPlanError):
            self._expand([{
                "kind": "parallel_join",
                "parallel": [{"role_type": 8}],
                "join": {"role_type": 6},
            }])

    def test_unknown_kind_raises(self):
        from lib.application.orchestration.dispatch.collab_plan import CollabPlanError
        with self.assertRaises(CollabPlanError):
            self._expand([{"kind": "loop_forever", "role_type": 8}])

    def test_collab_meta_grouping(self):
        from lib.application.orchestration.dispatch.collab_plan import collab_meta
        out = self._expand([{
            "kind": "parallel_join",
            "parallel": [{"role_type": 8}, {"role_type": 5}, {"role_type": 7}],
            "join": {"role_type": 12, "gate": "auto"},
        }])
        meta = collab_meta(out)
        self.assertEqual(len(meta["groups"]), 1)
        g = meta["groups"]["g1"]
        self.assertEqual(len(g["parallel"]), 3)
        self.assertEqual(g["join"]["role_type"], 12)
        self.assertEqual(g["join"]["gate"], "auto")


class TestCollabEngineParallelJoin(unittest.TestCase):
    """P0-1 引擎侧：并行组并发执行 → 组内等待 → 汇合 join（auto gate）。"""

    def _planned(self):
        from lib.application.orchestration.dispatch.collab_plan import expand_planned_chain_for_collab
        return expand_planned_chain_for_collab([{
            "kind": "parallel_join",
            "parallel": [{"role_type": 8}, {"role_type": 5}],
            "join": {"role_type": 12, "gate": "auto"},
        }], {})

    def test_chain_init_attaches_collab_join_meta(self):
        from lib.application.orchestration.pipeline.chain import init_chain_from_planned
        planned = self._planned()
        chain = init_chain_from_planned(
            planned, "c1", resolve_agent=lambda rt, pin, item=None: (f"agent{rt}", {"source": "test"}),
        )
        head = chain[0]
        self.assertIn("collab_join", head)
        meta = head["collab_join"]
        self.assertEqual(meta["total"], 2)
        self.assertEqual(meta["join_role_type"], 12)
        self.assertEqual(head["parallel_group"], meta["group_id"])
        # 兄弟/汇合不进入顺序队列
        self.assertFalse(head.get("planned_role_types"))

    def _task_with_parallel_members(self, tmp):
        from lib.application.orchestration.pipeline.chain import init_chain_from_planned
        planned = self._planned()
        chain = init_chain_from_planned(
            planned, "cv1", resolve_agent=lambda rt, pin, item=None: (f"agent{rt}", {"source": "test"}),
        )
        meta = chain[0]["collab_join"]
        # 模拟引擎已物化兄弟步骤并双双派发（都 await 结果）
        sib = {
            "step": 2, "step_id": "s1.p1", "role_type": 5,
            "to_role": "审查官", "to_person": "agent5", "to_agent": "agent5",
            "fsm_state": "awaiting_result", "status": "running",
            "task_id": "cv1", "result_ref": "msg-results/cv1/step-s1.p1.json",
            "parallel_group": meta["group_id"], "collab_join": meta,
        }
        chain.append(sib)
        chain[0]["fsm_state"] = "awaiting_result"
        chain[0]["status"] = "running"
        task = {
            "task_id": "cv1", "summary": "collab", "status": "running",
            "assignee": chain[0]["to_person"], "chain": chain,
            "fsm": {"state": "executing", "priority": 50},
            "updated_at": "2026-09-10T00:00:00+08:00",
        }
        _write(os.path.join(tmp, "tasks", "cv1.json"), task)
        return task

    def _apply(self, tmp, task, agent, conclusion):
        from lib.adapters.orchestration.task_fsm import apply_submit
        out = apply_submit(
            task, {"conclusion": conclusion, "summary": f"{agent} ok", "agent": agent},
            agents={"agent5": {}, "agent8": {}}, data_dir=tmp,
        )
        return out

    def test_parallel_await_then_join(self):
        from tests.test_helpers import seed_runtime_from_sot
        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            seed_runtime_from_sot(tmp)
            _seed_flow_sot(tmp)  # role-types/flow SoT：8/5/12 与候选 agentN
            task = self._task_with_parallel_members(tmp)
            first = self._apply(tmp, task, "agent5", "pass")
            self.assertEqual(first["action"], "parallel_await")
            second = self._apply(tmp, task, "agent8", "done")
            self.assertEqual(second["action"], "advance")
            self.assertEqual(second["next_role"], "验收员")
            self.assertEqual(len(task["chain"]), 3)
            self.assertEqual(task["chain"][-1]["role_type"], 12)

    def test_join_gate_review_then_approve(self):
        from lib.adapters.orchestration.task_fsm import apply_approve_join
        from lib.application.orchestration.dispatch.collab_plan import expand_planned_chain_for_collab
        from lib.application.orchestration.pipeline.chain import init_chain_from_planned
        from tests.test_helpers import seed_runtime_from_sot

        with tempfile.TemporaryDirectory(prefix="mailbus-gov-") as tmp:
            seed_runtime_from_sot(tmp)
            _seed_flow_sot(tmp)
            pj = [{
                "kind": "parallel_join",
                "parallel": [{"role_type": 8}, {"role_type": 5}],
                "join": {"role_type": 12, "gate": "review"},
            }]
            planned = expand_planned_chain_for_collab(pj, body={})
            chain = init_chain_from_planned(
                planned, "cv2",
                resolve_agent=lambda rt, pin, item=None: (f"agent{rt}", {"source": "test"}),
            )
            meta = chain[0]["collab_join"]
            self.assertEqual(meta.get("join_gate"), "review")
            sib = {
                "step": 2, "step_id": "s1.p1", "role_type": 5,
                "to_role": "审查官", "to_person": "agent5", "to_agent": "agent5",
                "fsm_state": "awaiting_result", "status": "running",
                "task_id": "cv2", "result_ref": "msg-results/cv2/step-s1.p1.json",
                "parallel_group": meta["group_id"], "collab_join": meta,
            }
            chain.append(sib)
            chain[0]["fsm_state"] = "awaiting_result"
            chain[0]["status"] = "running"
            chain[0]["to_person"] = "agent8"
            chain[0]["to_agent"] = "agent8"
            chain[0]["role_type"] = 8
            task = {
                "task_id": "cv2", "summary": "collab-review", "status": "running",
                "assignee": "agent8", "chain": chain,
                "fsm": {"state": "executing", "priority": 50},
                "updated_at": "2026-09-10T00:00:00+08:00",
            }
            _write(os.path.join(tmp, "tasks", "cv2.json"), task)
            first = self._apply(tmp, task, "agent5", "pass")
            self.assertEqual(first["action"], "parallel_await")
            second = self._apply(tmp, task, "agent8", "done")
            self.assertEqual(second["action"], "await_join_review")
            self.assertEqual(task["fsm"].get("substate"), "await_join_review")
            from lib.application.queries.manager import _bucket_of
            self.assertEqual(_bucket_of(task), "coordination")
            approved = apply_approve_join(task, {"reason": "ok"}, data_dir=tmp)
            self.assertTrue(approved.get("ok"))
            self.assertEqual(approved.get("action"), "advance")
            self.assertEqual(task["chain"][-1]["role_type"], 12)
