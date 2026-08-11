"""Wave F2: FakeRuntime / FakeResultStore main-path without real CLI."""
from __future__ import annotations

import unittest

from lib.infra.clock import FakeClock
from lib.adapters.fakes import FakeResultStore, FakeRuntime
from lib.domain.types import AgentRef, StepRef, StepResult
from lib.application.harness.contract import HarnessContract


class TestFakePorts(unittest.TestCase):
    def test_fake_runtime_spawn_no_cli(self) -> None:
        rt = FakeRuntime()
        agent = AgentRef(agent_id="lingyun", framework="claude_code", enabled=True)
        contract = HarnessContract(
            agent_id="lingyun",
            msg_id="m1",
            task_id="t1",
            step_id="s1",
        )
        handle = rt.spawn(agent, contract, timeout_seconds=12)
        self.assertEqual(handle.agent_id, "lingyun")
        self.assertEqual(handle.msg_id, "m1")
        self.assertIsNone(handle.pid)
        self.assertEqual(len(rt.spawns), 1)
        probe = rt.probe(agent)
        self.assertTrue(probe.ok)
        self.assertEqual(rt.push_timeout_seconds(agent), 30)

    def test_fake_result_store_write_read_ack(self) -> None:
        store = FakeResultStore()
        step = StepRef(task_id="task-1", step_id="01", attempt=1)
        path = store.write_step_result(
            StepResult(
                step=step,
                agent_id="lingyun",
                status="ok",
                path="",
                payload={"summary": "done"},
            )
        )
        self.assertTrue(path.startswith("memory://"))
        got = store.read_step_result(step)
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.status, "ok")
        self.assertEqual(got.payload.get("summary"), "done")
        unacked = store.list_unacked("lingyun", ["m1", "m2"])
        self.assertEqual(list(unacked), ["m1", "m2"])
        self.assertEqual(store.ack("lingyun", ["m1"]), 1)
        self.assertEqual(list(store.list_unacked("lingyun", ["m1", "m2"])), ["m2"])

    def test_fake_clock_importable_from_fakes(self) -> None:
        from lib.adapters.fakes import FakeClock as Reexported

        self.assertIs(Reexported, FakeClock)
        clock = FakeClock(100.0)
        clock.advance(5)
        self.assertEqual(clock.now_ts(), 105.0)


if __name__ == "__main__":
    unittest.main()
