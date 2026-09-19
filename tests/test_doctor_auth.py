"""doctor auth hardening — overbroad CIDR + OpenClaw change-me."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.adapters.ops.doctor_checks import (
    check_auth_hardening,
    check_compose_coupling,
    check_config_hygiene,
    _cidr_is_overbroad,
)


class TestCidrOverbroad(unittest.TestCase):
    def test_known_overbroad(self):
        self.assertTrue(_cidr_is_overbroad("0.0.0.0/0"))
        self.assertTrue(_cidr_is_overbroad("::/0"))

    def test_safe_cidrs(self):
        self.assertFalse(_cidr_is_overbroad("127.0.0.1/32"))
        self.assertFalse(_cidr_is_overbroad("172.16.0.0/12"))
        self.assertFalse(_cidr_is_overbroad(""))


class TestAuthHardening(unittest.TestCase):
    def test_overbroad_cidr_is_fail(self):
        items = check_auth_hardening(
            {
                "auth": {
                    "allow_write_without_token": True,
                    "write_without_token_cidrs": ["127.0.0.1/32", "0.0.0.0/0"],
                }
            }
        )
        fails = [i for i in items if i.level == "fail" and i.category == "auth"]
        self.assertTrue(any("过宽" in i.message for i in fails))

    def test_legacy_exempt_cidrs_also_scanned(self):
        items = check_auth_hardening({"exempt_cidrs": ["::/0"]})
        fails = [i for i in items if i.level == "fail"]
        self.assertTrue(any("过宽" in i.message for i in fails))

    def test_default_token_required_ok(self):
        items = check_auth_hardening({"auth": {"allow_write_without_token": False}})
        self.assertTrue(any(i.level == "ok" and "Token" in i.message for i in items))

    def test_cors_star_is_warn(self):
        items = check_auth_hardening({"auth": {"cors_origins": ["*"]}})
        self.assertTrue(any(i.level == "warn" and "CORS" in i.message and "*" in i.message for i in items))

    def test_cors_explicit_ok(self):
        items = check_auth_hardening({"auth": {"cors_origins": ["http://127.0.0.1:9814"]}})
        self.assertTrue(any(i.level == "ok" and "CORS" in i.message for i in items))
        self.assertFalse(any(i.level == "warn" and "CORS" in i.message for i in items))

    def test_openclaw_change_me_warn_not_fail(self):
        # P10 batch: push (docker exec) does not need the gateway token, so a
        # missing/default token must not fail doctor overall — it warns.
        with patch.dict(os.environ, {"OPENCLAW_GATEWAY_TOKEN": "change-me"}, clear=False):
            with patch(
                "lib.adapters.config.browser_auth.openclaw_gateway_token",
                return_value="change-me",
            ):
                items = check_auth_hardening(
                    {
                        "agents": {
                            "agent-c": {"type": "openclaw", "enabled": True},
                        }
                    }
                )
        self.assertFalse(any(i.level == "fail" and "Token" in i.message for i in items))
        warns = [i for i in items if i.level == "warn" and "Token" in i.message]
        self.assertEqual(len(warns), 1)

    def test_openclaw_real_token_ok(self):
        with patch(
            "lib.adapters.config.browser_auth.openclaw_gateway_token",
            return_value="real-secret-token",
        ):
            items = check_auth_hardening(
                {"agents": {"agent-c": {"type": "openclaw", "enabled": True}}}
            )
        self.assertTrue(any(i.level == "ok" and "OpenClaw" in i.message for i in items))
        self.assertFalse(any(i.level == "fail" and "change-me" in i.message for i in items))


class TestConfigHygiene(unittest.TestCase):
    def test_empty_chains_warn(self):
        items = check_config_hygiene({})
        warns = [i for i in items if i.level == "warn" and i.category == "config"]
        self.assertTrue(any("mailbus_chains" in i.message for i in warns))

    def test_empty_templates_list_warn(self):
        items = check_config_hygiene({"mailbus_chains": {"templates": [], "daily_budget_cny": 10}})
        self.assertTrue(any(i.level == "warn" and "无有效链路模板" in i.message for i in items))

    def test_valid_template_ok(self):
        items = check_config_hygiene(
            {
                "mailbus_chains": {
                    "daily_budget_cny": 30,
                    "templates": [{"id": "default-dev", "default": True}],
                }
            }
        )
        self.assertTrue(any(i.level == "ok" and "模板 1" in i.message for i in items))
        self.assertFalse(any(i.level == "warn" and "无有效链路模板" in i.message for i in items))


class TestComposeCoupling(unittest.TestCase):
    def test_repo_compose_clean(self):
        from lib.infra.constants import MAILBUS_ROOT

        items = check_compose_coupling(mail_root=Path(MAILBUS_ROOT))
        fails = [i for i in items if i.level == "fail"]
        self.assertFalse(fails, [(i.message, i.detail) for i in fails])
        self.assertTrue(any(i.level == "ok" for i in items))

    def test_detects_bad_marker(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            da = base / "docker-agents"
            da.mkdir()
            (da / "docker-compose.yml").write_text(
                "volumes:\n  - ${X:-../../Agent/docker/codex}:/w\n",
                encoding="utf-8",
            )
            items = check_compose_coupling(mail_root=base)
            self.assertTrue(any(i.level == "fail" for i in items))

    def test_env_absolute_agent_path_ok(self):
        """显式绝对路径指向本机 Agent 树 = 配置关联，不告警。"""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            da = base / "docker-agents"
            da.mkdir()
            (da / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
            (da / ".env").write_text(
                "OPENCLAW_WORKSPACE=/mnt/e/ai_tools/Agent/docker/openclaw_space\n",
                encoding="utf-8",
            )
            items = check_compose_coupling(mail_root=base)
            self.assertFalse(
                any(i.level == "warn" and ".env" in i.message and "相对" in i.message for i in items),
                [(i.level, i.message) for i in items],
            )
            self.assertTrue(any(i.level == "ok" and ".env" in i.message for i in items))

    def test_env_relative_agent_default_warn(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            da = base / "docker-agents"
            da.mkdir()
            (da / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
            (da / ".env").write_text(
                "OPENCLAW_WORKSPACE=../../Agent/docker/openclaw_space\n",
                encoding="utf-8",
            )
            items = check_compose_coupling(mail_root=base)
            self.assertTrue(
                any(i.level == "warn" and ".env" in i.message for i in items),
                [(i.level, i.message) for i in items],
            )


if __name__ == "__main__":
    unittest.main()
