"""Wave F1: FileConfigRepository — lock-held RMW + agent refs."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest

from lib.adapters.config.composite_config import CompositeConfigRepo
from lib.adapters.config.file_repo import FileConfigRepository
from lib.composition import AppContext, bind_data_dir, build_config_repo, reset_context


class TestFileConfigRepository(unittest.TestCase):
    def tearDown(self) -> None:
        reset_context()

    def test_update_and_list_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = FileConfigRepository(tmp)
            repo.update(
                lambda cfg: cfg.update(
                    {
                        "agents": {
                            "a1": {
                                "type": "codex",
                                "role": "dev",
                                "enabled": True,
                                "mount_mode": "host",
                            }
                        }
                    }
                )
            )
            refs = repo.list_agents()
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0].agent_id, "a1")
            self.assertEqual(refs[0].framework, "codex")
            self.assertEqual(refs[0].role_id, "dev")
            self.assertEqual(refs[0].mount, "host")
            self.assertTrue(refs[0].enabled)
            got = repo.get_agent("a1")
            self.assertIsNotNone(got)
            self.assertIsNone(repo.get_agent("missing"))
            mtime = repo.agent_config_mtime("a1")
            self.assertIsNotNone(mtime)
            self.assertIsNone(repo.agent_config_mtime("missing"))

    def test_update_holds_lock(self) -> None:
        """Mutate + write run while file_lock context is held."""
        import contextlib
        from unittest import mock

        import lib.adapters.config.file_repo as file_repo_mod

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            events: list[str] = []
            real_lock = file_repo_mod.file_lock
            real_write = FileConfigRepository._write_unlocked

            @contextlib.contextmanager
            def spy_lock(timeout: float = 10.0, path: str = ""):
                events.append("enter")
                with real_lock(timeout=timeout, path=path):
                    events.append("holding")
                    try:
                        yield
                    finally:
                        events.append("before_release")
                events.append("released")

            def spy_write(repo_self: FileConfigRepository, data: dict) -> None:
                self.assertIn("holding", events)
                self.assertNotIn("released", events)
                events.append("write")
                real_write(repo_self, data)

            with mock.patch.object(file_repo_mod, "file_lock", spy_lock):
                with mock.patch.object(FileConfigRepository, "_write_unlocked", spy_write):
                    repo = FileConfigRepository(tmp)

                    def mut(cfg: dict) -> None:
                        self.assertIn("holding", events)
                        self.assertNotIn("released", events)
                        events.append("mutate")
                        cfg["agents"] = {"x": {"type": "none"}}

                    repo.update(mut)

            self.assertEqual(events[0], "enter")
            self.assertIn("holding", events)
            self.assertLess(events.index("mutate"), events.index("write"))
            self.assertLess(events.index("write"), events.index("before_release"))
            self.assertEqual(events[-1], "released")
            with open(path, encoding="utf-8") as f:
                self.assertIn("x", json.load(f).get("agents", {}))

    def test_concurrent_updates_preserve_both(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = FileConfigRepository(tmp, lock_timeout=10.0)
            repo.update(lambda cfg: cfg.setdefault("agents", {}))
            barrier = threading.Barrier(2)
            errors: list[BaseException] = []

            def bump(key: str) -> None:
                try:
                    barrier.wait(timeout=5.0)

                    def mut(cfg: dict) -> None:
                        agents = cfg.setdefault("agents", {})
                        agents[key] = {"type": "codex", "enabled": True}

                    repo.update(mut)
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            t1 = threading.Thread(target=bump, args=("a",), daemon=True)
            t2 = threading.Thread(target=bump, args=("b",), daemon=True)
            t1.start()
            t2.start()
            t1.join(timeout=10.0)
            t2.join(timeout=10.0)
            self.assertEqual(errors, [])
            agents = repo.get_raw().get("agents") or {}
            self.assertIn("a", agents)
            self.assertIn("b", agents)

    def test_build_config_repo_and_bind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_config_repo(tmp)
            self.assertIsInstance(repo, CompositeConfigRepo)
            ctx = bind_data_dir(tmp)
            self.assertIsNotNone(ctx.config_repo)
            json_path = getattr(getattr(ctx.config_repo, "_json", None), "_path", None) or getattr(
                ctx.config_repo, "_path", None
            )
            self.assertEqual(
                os.path.normpath(json_path),
                os.path.normpath(os.path.join(tmp, "config.json")),
            )
            ctx2 = AppContext(data_dir=tmp)
            self.assertIsInstance(ctx2.ensure_config_repo(), CompositeConfigRepo)


if __name__ == "__main__":
    unittest.main()
