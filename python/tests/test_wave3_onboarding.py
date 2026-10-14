"""Wave 3 E4/E5: instance-card derivation + assembly result card."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDerivedDockerStamp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # hermes 原生 profiles 目录 → 可被发现的角色
        self.install = os.path.join(self.tmp, "hermes-root")
        os.makedirs(os.path.join(self.install, "profiles", "role-x"), exist_ok=True)
        cfg = {
            "agents": {},
            "agent_instances": {
                "inst-hermes": {
                    "id": "inst-hermes", "type": "hermes_profile", "run_target": "docker",
                    "install_path": self.install, "role_ids": [],
                },
            },
        }
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_role_load_stamps_derived_docker(self):
        from lib.adapters.config.instance_roles import load_roles_for_instance

        out = load_roles_for_instance(self.tmp, "inst-hermes")
        self.assertIn("role-x", out["role_ids"])
        with open(os.path.join(self.tmp, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        rec = cfg["agents"]["role-x"]
        # E4：docker 服务/管线从框架默认派生并显式落卡（可单点覆盖）
        self.assertEqual(rec["docker"]["service"], "hermes")
        self.assertEqual(rec["docker"]["profile"], "role-x")
        self.assertTrue(rec["docker"].get("_derived"))

    def test_existing_docker_not_overwritten(self):
        from lib.adapters.config.instance_roles import load_roles_for_instance

        with open(os.path.join(self.tmp, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["agents"]["role-x"] = {"type": "hermes_profile", "enabled": True,
                                   "docker": {"service": "my-custom-svc"}}
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        load_roles_for_instance(self.tmp, "inst-hermes")
        with open(os.path.join(self.tmp, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg["agents"]["role-x"]["docker"]["service"], "my-custom-svc")


class TestAssemblyCard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        cfg = {
            "agents": {
                "worker-1": {
                    "type": "codex", "enabled": True, "instance_id": "inst-codex",
                    "models": ["deepseek-flash"],
                },
            },
            "agent_instances": {
                "inst-codex": {"id": "inst-codex", "type": "codex",
                               "last_smoke_ok_at": "2026-09-20T10:00:00+0800"},
            },
        }
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_card_sections_and_effective_push(self):
        from lib.adapters.config.assembly_card import assembly_card

        card = assembly_card(self.tmp, "worker-1")
        self.assertEqual(card["framework"], "codex")
        for key in ("skills", "rules", "persona", "push"):
            self.assertIn(key, card)
        self.assertIn("final", card["skills"])
        # push 实际通道：容器/管线按框架默认派生（E4 语义的最终事实）
        self.assertIn("codex", card["push"]["container"])
        self.assertEqual(card["push"]["model"], "deepseek-flash")
        # 上次实测投递成功时间透出
        self.assertEqual(card["last_smoke_ok_at"], "2026-09-20T10:00:00+0800")

    def test_unknown_agent_raises(self):
        from lib.adapters.config.assembly_card import assembly_card

        with self.assertRaises(ValueError):
            assembly_card(self.tmp, "ghost")


class TestChannelsTypeFallback(unittest.TestCase):
    def test_cli_frameworks_resolve_local_cli_via_type(self):
        from lib.core.a2a.agent_card_cache import enrich_agent_channels

        for fw in ("claude_code", "codex", "opencode"):
            merged = enrich_agent_channels("new-role", {"type": fw})
            self.assertEqual(merged.get("transport"), "local_cli", fw)
            self.assertFalse((merged.get("channels") or {}).get("a2a", {}).get("enabled"), fw)


class TestSmokeStamp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        cfg = {
            "agents": {"demo-a": {"type": "none", "instance_id": "inst-none", "enabled": True}},
            "agent_instances": {
                "inst-none": {"id": "inst-none", "type": "none", "run_target": "windows",
                              "role_ids": ["demo-a"], "enabled": True},
            },
        }
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_green_stamps_last_smoke_ok_at(self):
        from lib.adapters.ops.connection_test import run_connection_test

        def _ack_later():
            time.sleep(1.0)
            inbox_dir = os.path.join(self.tmp, "inbox", "demo-a")
            for _ in range(50):
                p = os.path.join(inbox_dir, "inbox.json")
                if os.path.isfile(p):
                    break
                time.sleep(0.1)
            with open(p, encoding="utf-8") as f:
                msgs = json.load(f).get("messages") or []
            smoke = [m["id"] for m in msgs if str(m["id"]).startswith("smoke-")]
            with open(os.path.join(inbox_dir, "ack.json"), "w", encoding="utf-8") as f:
                json.dump([{"action": "ack", "msg_id": smoke[-1], "agent": "demo-a"}], f)

        threading.Thread(target=_ack_later, daemon=True).start()
        report = run_connection_test(self.tmp, "inst-none", ack_timeout_sec=15, auto_load_roles=False)
        self.assertTrue(report["ok"], msg=str(report))
        with open(os.path.join(self.tmp, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        stamped = cfg["agent_instances"]["inst-none"].get("last_smoke_ok_at") or ""
        self.assertTrue(stamped.startswith("20"), stamped)


if __name__ == "__main__":
    unittest.main()
