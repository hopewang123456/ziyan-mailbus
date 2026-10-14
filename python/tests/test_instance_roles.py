"""instance_roles 单元测试 — 原生角色目录扫描（_discover_native_roles / discover_roles_for_instance）。

自包含：用 tempfile 构造框架原生目录 + fixture vault path-map，不依赖本机 Vault。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib.adapters.config.instance_roles import (
    _discover_native_roles,
    discover_roles_for_instance,
)

FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"


def _write(p: Path, text: str = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


class TestDiscoverNativeRoles(unittest.TestCase):
    def test_hermes_profiles(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root / "profiles" / "agent-a" / "SOUL.md")
            _write(root / "profiles" / ".hidden" / "SOUL.md")
            roles = _discover_native_roles("hermes", td)
            self.assertEqual(set(roles), {"agent-a"})
            self.assertEqual(roles["agent-a"]["source"], "native-profiles")

    def test_openclaw_identity_and_profile(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root / "foo" / "SOUL.md")  # 身份目录
            _write(root / "bar" / "IDENTITY.md")  # 身份目录（IDENTITY 也算）
            (root / "data" / ".openclaw-agent-m").mkdir(parents=True)  # profile 兜底
            (root / "skills").mkdir()  # 共享，跳过
            (root / ".git").mkdir()  # 隐藏，跳过
            _write(root / "memory" / "SOUL.md")  # 共享目录即便有 SOUL 也跳过
            roles = _discover_native_roles("openclaw", td)
            self.assertEqual(set(roles), {"foo", "bar", "agent-m"})
            self.assertEqual(roles["foo"]["source"], "native-identity-dir")
            self.assertEqual(roles["agent-m"]["source"], "native-profile-dir")

    def test_claude_code_profiles(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / ".claude-lingyan").mkdir()
            (home / ".claude-lingyun").mkdir()
            (home / ".claude").mkdir()  # 全局目录，跳过
            with mock.patch("pathlib.Path.home", return_value=home):
                roles = _discover_native_roles("claude_code", "ignored")
            self.assertEqual(set(roles), {"lingyan", "lingyun"})

    def test_codex_agents(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root / "agents" / "lingjian" / "IDENTITY.md")
            _write(root / "agents" / "skills" / "IDENTITY.md")  # 共享，跳过
            roles = _discover_native_roles("codex", td)
            self.assertEqual(set(roles), {"lingjian"})

    def test_opencode_multi_role_dir_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root / "SOUL.md")  # 单项目根不算角色
            _write(root / "dali" / "SOUL.md")  # 子目录含身份文件算角色
            roles = _discover_native_roles("opencode", td)
            self.assertEqual(set(roles), {"dali"})

    def test_skip_ids_filtered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root / "profiles" / "agent-a" / "SOUL.md")
            roles = _discover_native_roles("hermes", td, skip_ids={"agent-a"})
            self.assertEqual(roles, {})


class TestDiscoverRolesForInstance(unittest.TestCase):
    def test_native_merges_without_override(self):
        with mock.patch(
            "lib.adapters.config.instance_roles._path_map",
            return_value={
                "vault_root": str(FIXTURE_VAULT),
                "persons": {
                    "agent-a": {"framework": "hermes", "display_name": "A"},
                    "lingzhao": {"framework": "openclaw", "display_name": "Zhao"},
                },
            },
        ):
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                _write(root / "profiles" / "agent-a" / "SOUL.md")
                _write(root / "profiles" / "agent-b" / "SOUL.md")
                roles = discover_roles_for_instance({"type": "hermes", "install_path": td})
                ids = {r["id"] for r in roles}
                # path-map 的 agent-a 保留（display_name=A），native agent-b 兜底补充
                self.assertIn("agent-a", ids)
                self.assertIn("agent-b", ids)
                # lingzhao 属其它框架，不该被 hermes 原生扫描带出
                self.assertNotIn("lingzhao", ids)
                a = next(r for r in roles if r["id"] == "agent-a")
                self.assertEqual(a["display_name"], "A")
                b = next(r for r in roles if r["id"] == "agent-b")
                self.assertEqual(b["source"], "native-profiles")


if __name__ == "__main__":
    unittest.main()
