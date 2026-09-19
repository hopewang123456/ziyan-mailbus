"""Wave 4 工位模型：注册表迁移 / 在岗解析 / 空缺零 token 进裁决 / 裁决后流转。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.application.ops.stations_migrate import derive_stations, migrate_stations
from lib.application.orchestration.dispatch.station_resolver import (
    resolve_agent_for_station,
    station_registry,
)


def _seed(data_dir: str, *, worker_enabled: bool = True) -> None:
    os.makedirs(os.path.join(data_dir, "roles", "json"), exist_ok=True)
    os.makedirs(os.path.join(data_dir, "tasks"), exist_ok=True)
    with open(os.path.join(data_dir, "roles", "json", "role-types.json"), "w", encoding="utf-8") as f:
        json.dump({"roles": {
            "8": {"key": "developer", "display": {"zh": "开发工程师"},
                  "candidates": ["worker-1", "worker-2"]},
        }}, f, ensure_ascii=False)
    with open(os.path.join(data_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump({
            "agents": {
                "worker-1": {"type": "none", "enabled": worker_enabled},
                "worker-2": {"type": "none", "enabled": worker_enabled},
                "other": {"type": "none", "enabled": True},
            },
            "org_defaults": {"reviewer": "other", "notify_agents": ["other"], "audit_reviewers": ["other", "other"]},
            "transport": {"use_router": True},
            "harness": {"mode": "production"},
        }, f, ensure_ascii=False)


class TestMigrate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_migrate_derives_and_is_idempotent(self):
        out = migrate_stations(self.tmp)
        self.assertIn("developer", out["created"])
        self.assertIn("reviewer", out["created"])
        reg = station_registry(self.tmp)
        self.assertEqual(reg["developer"]["candidates"], ["worker-1", "worker-2"])
        self.assertEqual(reg["developer"]["role_type"], 8)
        # org 派生候选去重
        self.assertEqual(reg["reviewer"]["candidates"], ["other"])
        # 幂等：再跑保留已有
        out2 = migrate_stations(self.tmp)
        self.assertIn("developer", out2["skipped_preserved"])
        # 版本号
        with open(os.path.join(self.tmp, "config.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["stations_version"], 1)

    def test_derive_empty_store(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        self.assertEqual(derive_stations(empty), {})


class TestStationResolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed(self.tmp)
        migrate_stations(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_available_in_order(self):
        agent, meta = resolve_agent_for_station(self.tmp, "developer")
        self.assertEqual(agent, "worker-1")
        self.assertEqual(meta["source"], "station")
        agent2, _ = resolve_agent_for_station(self.tmp, "developer", exclude={"worker-1"})
        self.assertEqual(agent2, "worker-2")

    def test_vacancy_when_all_unavailable(self):
        with open(os.path.join(self.tmp, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        for a in ("worker-1", "worker-2"):
            cfg["agents"][a]["enabled"] = False
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        agent, meta = resolve_agent_for_station(self.tmp, "developer")
        self.assertEqual(agent, "")
        self.assertTrue(meta.get("vacancy"))
        self.assertEqual(meta["policy"], "adjudicate")

    def test_unknown_station(self):
        agent, meta = resolve_agent_for_station(self.tmp, "ghost")
        self.assertEqual(agent, "")
        self.assertEqual(meta.get("error"), "unknown_station")


class TestPlannerStation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed(self.tmp)
        migrate_stations(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_explicit_station_entry_resolves_and_carries(self):
        from lib.application.orchestration.router.planner import plan_tier0

        env = {
            "task_id": "stn-plan-1", "intent": "x", "initiator": "t", "mode": "explicit", "tier": "S",
            "planned_chain": [{"station": "developer", "reason": "r"}],
        }
        out = plan_tier0(env, data_dir=self.tmp)
        item = out["planned_chain"][0]
        self.assertEqual(item["role_type"], 8)
        self.assertEqual(item["station"], "developer")

    def test_unknown_station_rejected(self):
        from lib.application.orchestration.router.planner import PlanError, plan_tier0

        env = {
            "task_id": "stn-plan-2", "intent": "x", "initiator": "t", "mode": "explicit", "tier": "S",
            "planned_chain": [{"station": "ghost", "reason": "r"}],
        }
        with self.assertRaises(PlanError):
            plan_tier0(env, data_dir=self.tmp)


class TestVacancyAcceptance(unittest.TestCase):
    """SoT Wave 4 验收：全空缺 → 裁决队列且零 token；裁决改派后正常流转。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed(self.tmp, worker_enabled=False)  # developer 工位全空缺
        migrate_stations(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _create_task(self, task_id: str) -> dict:
        from lib.application.orchestration.router.envelope_validate import validate_envelope
        from lib.application.orchestration.router.planner import plan_tier0
        from lib.application.orchestration.tracker import TaskTracker
        from lib.application.orchestration.router.dispatch import dispatch_first_step, start_executing

        env = {
            "task_id": task_id, "intent": "工位空缺验收", "initiator": "t",
            "mode": "explicit", "tier": "S",
            "planned_chain": [{"station": "developer", "reason": "执行"}],
        }
        self.assertEqual(validate_envelope(env, data_dir=self.tmp), [])
        out = plan_tier0(env, data_dir=self.tmp)
        tr = TaskTracker(self.tmp)
        task = tr.create_from_envelope(env, planned_chain=out["planned_chain"], plan_meta=out["plan_meta"])
        start_executing(task)
        return task

    def test_vacancy_blocked_zero_token_then_adjudicated(self):
        from lib.application.orchestration.human_queue_resolve import apply_human_queue_resolution
        from lib.adapters.orchestration.human_queue import close_item
        from lib.infra.token_ledger import by_task

        task = self._create_task("demo-vac-1")
        from lib.application.orchestration.router.dispatch import dispatch_first_step

        dispatched = dispatch_first_step(self.tmp, task)
        self.assertFalse(dispatched)
        self.assertEqual(task["status"], "blocked")
        self.assertEqual(task["fsm"]["reason"], "station_vacant:developer")

        # 待裁决队列（E8 来源标签）
        with open(os.path.join(self.tmp, "human-queue.json"), encoding="utf-8") as f:
            hq = json.load(f)
        items = [e for e in hq.get("items") or [] if e.get("source") == "station_vacancy" and e.get("status") == "pending"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "station_vacancy")

        # 零 token：无 inbox 投递、无台账
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "ledger")) or by_task(self.tmp, "demo-vac-1"))
        inbox_dir = os.path.join(self.tmp, "inbox", "worker-1")
        self.assertFalse(os.path.isfile(os.path.join(inbox_dir, "inbox.json")))

        # 裁决：临时指名 other（direct 模式）→ 重推成功
        item = items[0]
        close_item(self.tmp, item["id"], {"decision": "approved", "reviewer": "ziyan"})
        out = apply_human_queue_resolution(self.tmp, item, {"decision": "approved", "agent": "other"})
        self.assertTrue(out["ok"], msg=str(out))
        self.assertEqual(out["action"], "vacancy_redispatched")
        with open(os.path.join(self.tmp, "tasks", "demo-vac-1.json"), encoding="utf-8") as f:
            t = json.load(f)
        self.assertEqual(t["status"], "running")
        self.assertEqual(t["chain"][0]["fsm_state"], "dispatched")
        self.assertEqual(t["chain"][0]["to_agent"], "other")
        # 投递真实发生
        with open(os.path.join(self.tmp, "inbox", "other", "inbox.json"), encoding="utf-8") as f:
            ib = json.load(f)
        self.assertTrue(any(m.get("task_id") == "demo-vac-1" for m in ib["messages"]))


class TestTemplates(unittest.TestCase):
    def test_station_templates_present(self):
        from lib.infra.constants import MAILBUS_ROOT

        path = os.path.join(str(MAILBUS_ROOT), "config", "mailbus", "task-templates.json")
        with open(path, encoding="utf-8") as f:
            tpls = json.load(f).get("templates") or []
        ids = {t["id"] for t in tpls}
        self.assertTrue(ids >= {"single-step-station", "code-pipeline", "external-trigger"})
        for t in tpls:
            if t["id"].endswith("-station") or t["id"] in ("code-pipeline", "external-trigger"):
                for st in (t.get("envelope") or {}).get("planned_chain") or []:
                    self.assertTrue(st.get("station"), t["id"])


if __name__ == "__main__":
    unittest.main()
