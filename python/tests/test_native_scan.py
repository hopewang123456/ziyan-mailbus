"""native_scan 单元测试 — agent 安装路径资产扫描。

依赖本机 Vault 的 _path-map.json 时通过 tests/fixtures/vault/_path-map.json
自包含 fixture（AGENT_VAULT_ROOT 指向 fixture），保证 CI / 干净环境可跑。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib.adapters.config.native_scan import (
    identity_file_candidates,
    path_map_mounts_for,
    scan_agent_assets,
)

FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"


def _patch_vault() -> mock._patch:
    return mock.patch("lib.adapters.config.native_scan.AGENT_VAULT_ROOT", FIXTURE_VAULT)


class TestPathMapMounts(unittest.TestCase):
    def test_hermes_mounts_match(self):
        with _patch_vault():
            mounts = path_map_mounts_for("hermes", "agent-a")
        # 多个 hermes 人物只有 agent-a 的挂载（ids 过滤）
        self.assertTrue(mounts)
        for m in mounts:
            self.assertEqual(m.get("framework"), "hermes")
        # 两类挂载：skills（target 03-shared）+ memory（target persons/…）
        targets = " ".join(m.get("target", "") for m in mounts)
        self.assertIn("03-shared", targets)
        self.assertIn("memory", targets)

    def test_claude_mounts_filter_by_agent(self):
        with _patch_vault():
            mounts = path_map_mounts_for("claude_code", "agent-b")
        self.assertTrue(any(".claude-agent-b" in m.get("native", "") for m in mounts))
        self.assertFalse(any(".claude-agent-c" in m.get("native", "") for m in mounts))


class TestIdentityCandidates(unittest.TestCase):
    def test_hermes_soul(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "profiles" / "agent-a").mkdir(parents=True)
            (root / "profiles" / "agent-a" / "SOUL.md").write_text("x", encoding="utf-8")
            cands = identity_file_candidates("hermes", "agent-a", td)
            self.assertTrue(any(c["exists"] for c in cands))

    def test_codex_identity(self):
        cands = identity_file_candidates("codex", "agent-c", "")
        self.assertTrue(all(c.get("kind") == "identity" for c in cands))
        self.assertTrue(any("IDENTITY.md" in c["path"] for c in cands))


class TestScanAgentAssets(unittest.TestCase):
    def test_hermes_scan_shapes(self):
        with _patch_vault():
            r = scan_agent_assets("hermes", "agent-a", "<HERMES_DATA>/.hermes", data_dir="store")
        self.assertEqual(r["framework"], "hermes")
        self.assertEqual(r["agent_id"], "agent-a")
        self.assertIn("assets", r)
        self.assertIn("found", r)
        self.assertIn("missing", r)
        self.assertIn("paths", r["assets"][0])
        # 三端路径
        p0 = r["assets"][0]["paths"]
        self.assertIn("windows", p0)
        self.assertIn("wsl", p0)
        self.assertIn("docker", p0)
        # skills 路径应落在 profiles/agent-a/skills
        skills = [a for a in r["assets"] if a["kind"] == "skills"]
        self.assertTrue(skills)
        self.assertIn("profiles", skills[0]["paths"]["windows"])

    def test_claude_scan_override_root(self):
        # install_root 与模板根前缀一致 → 直接用模板路径
        with _patch_vault():
            r = scan_agent_assets("claude_code", "agent-b", r"%USERPROFILE%/.claude-agent-b", data_dir="store")
        skill_paths = [a for a in r["assets"] if a["kind"] == "skills"]
        self.assertTrue(skill_paths)
        windows_paths = " ".join(a["paths"]["windows"] for a in skill_paths)
        self.assertIn(".claude-agent-b", windows_paths)

    def test_identity_kind_present(self):
        with _patch_vault():
            r = scan_agent_assets("opencode", "agent-d", "<OPENCODE_ROOT>", data_dir="store")
        kinds = {a["kind"] for a in r["assets"]}
        self.assertIn("identity", kinds)
        self.assertIn("skills", kinds)


class TestScanApiHandler(unittest.TestCase):
    def test_scan_saves_install_path_and_enables(self):
        from lib.api.handlers_lifecycle import handle_agent_scan

        with tempfile.TemporaryDirectory() as td:
            install = tempfile.mkdtemp()  # 真实存在的路径 → gate 通过
            cfg = {
                "agent_instances": {
                    "inst-x": {"id": "inst-x", "type": "hermes_profile", "run_target": "docker",
                               "install_path": "", "host": "127.0.0.1", "role_ids": ["agent-a"]}
                },
                "agents": {"agent-a": {"type": "hermes_profile", "instance_id": "inst-x", "enabled": False}},
            }
            Path(td, "config.json").write_text(json.dumps(cfg), encoding="utf-8")

            class _H:
                def __init__(self):
                    self.data_dir = td
                    self._b = {"instance_id": "inst-x", "framework": "hermes_profile",
                               "install_path": install, "run_target": "windows"}
                    self.status = 200
                    self.payload = None

                def _read_post_body(self):
                    return self._b

                def _send_json(self, payload, status=200):
                    self.payload = payload
                    self.status = status

            h = _H()
            with _patch_vault():
                handle_agent_scan(h)
            self.assertEqual(h.status, 200)
            self.assertEqual(h.payload.get("install_path"), install)
            self.assertTrue(h.payload.get("gate", {}).get("passed"))
            saved = json.loads(Path(td, "config.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["agent_instances"]["inst-x"]["install_path"], install)
            self.assertEqual(saved["agent_instances"]["inst-x"]["run_target"], "windows")
            self.assertTrue(saved["agent_instances"]["inst-x"]["gate_passed"])
            # 角色级 enabled 是退役/工作手动开关，不由扫描覆盖
            self.assertFalse(saved["agents"]["agent-a"]["enabled"])

    def test_scan_missing_path_disables(self):
        from lib.api.handlers_lifecycle import handle_agent_scan

        with tempfile.TemporaryDirectory() as td:
            cfg = {
                "agent_instances": {
                    "inst-x": {"id": "inst-x", "type": "hermes_profile", "run_target": "windows",
                               "install_path": "", "host": "127.0.0.1", "role_ids": ["agent-a"]}
                },
                "agents": {"agent-a": {"type": "hermes_profile", "instance_id": "inst-x", "enabled": True}},
            }
            Path(td, "config.json").write_text(json.dumps(cfg), encoding="utf-8")

            class _H:
                def __init__(self):
                    self.data_dir = td
                    self._b = {"instance_id": "inst-x", "framework": "hermes_profile",
                               "install_path": "Z:/definitely/missing/path", "run_target": "windows"}
                    self.status = 200
                    self.payload = None

                def _read_post_body(self):
                    return self._b

                def _send_json(self, payload, status=200):
                    self.payload = payload
                    self.status = status

            h = _H()
            with _patch_vault():
                handle_agent_scan(h)
            self.assertEqual(h.status, 200)
            self.assertFalse(h.payload.get("gate", {}).get("passed"))
            self.assertFalse(h.payload.get("gate_passed"))
            saved = json.loads(Path(td, "config.json").read_text(encoding="utf-8"))
            self.assertFalse(saved["agent_instances"]["inst-x"]["gate_passed"])
            # 角色级 enabled 保持原值（不被门禁覆盖）
            self.assertTrue(saved["agents"]["agent-a"]["enabled"])

    def test_scan_run_target_coerced_to_matrix(self):
        from lib.api.handlers_lifecycle import handle_agent_scan

        with tempfile.TemporaryDirectory() as td:
            cfg = {
                "agent_instances": {
                    "inst-c": {"id": "inst-c", "type": "claude_code", "run_target": "windows",
                               "install_path": "", "host": "127.0.0.1", "role_ids": ["agent-b"]}
                },
                "agents": {"agent-b": {"type": "claude_code", "instance_id": "inst-c", "enabled": False}},
            }
            Path(td, "config.json").write_text(json.dumps(cfg), encoding="utf-8")

            class _H:
                def __init__(self):
                    self.data_dir = td
                    self._b = {"instance_id": "inst-c", "framework": "claude_code",
                               "install_path": td, "run_target": "docker"}
                    self.status = 200
                    self.payload = None

                def _read_post_body(self):
                    return self._b

                def _send_json(self, payload, status=200):
                    self.payload = payload
                    self.status = status

            h = _H()
            with _patch_vault():
                handle_agent_scan(h)
            # claude_code 不支持 docker 端 → 回落到第一个可用端 windows
            self.assertEqual(h.payload.get("run_target"), "windows")
            saved = json.loads(Path(td, "config.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["agent_instances"]["inst-c"]["run_target"], "windows")

    def test_scan_unknown_instance_404(self):
        from lib.api.handlers_lifecycle import handle_agent_scan

        with tempfile.TemporaryDirectory() as td:
            Path(td, "config.json").write_text(
                json.dumps({"agent_instances": {}, "agents": {}}), encoding="utf-8"
            )

            class _H:
                def __init__(self):
                    self.data_dir = td
                    self.status = 200
                    self.payload = None

                def _read_post_body(self):
                    return {"instance_id": "ghost", "framework": "codex", "install_path": ""}

                def _send_json(self, payload, status=200):
                    self.payload = payload
                    self.status = status

            h = _H()
            handle_agent_scan(h)
            self.assertEqual(h.status, 404)


class TestFrameworkDiscovery(unittest.TestCase):
    def test_run_target_matrix(self):
        from lib.adapters.frameworks.framework_discovery import framework_run_targets

        for fw in ("hermes", "hermes_profile", "openclaw", "codex", "opencode"):
            self.assertEqual(framework_run_targets(fw), ["windows", "wsl", "linux", "docker"], fw)
        self.assertEqual(framework_run_targets("claude_code"), ["windows", "wsl", "linux"])
        self.assertEqual(framework_run_targets("cursor"), ["windows"])
        self.assertEqual(framework_run_targets("cline"), ["windows", "wsl", "linux"])
        self.assertEqual(framework_run_targets("none"), ["windows"])
        self.assertEqual(framework_run_targets("unknown"), ["windows"])

    def test_default_install_path_claude_env_preferred(self):
        from lib.adapters.frameworks.framework_discovery import framework_default_install_path

        prev = os.environ.get("CLAUDE_WORKSPACE_ROOT")
        try:
            os.environ["CLAUDE_WORKSPACE_ROOT"] = r"D:\my-claude"
            self.assertEqual(framework_default_install_path("claude_code"), r"D:\my-claude")
        finally:
            if prev is None:
                os.environ.pop("CLAUDE_WORKSPACE_ROOT", None)
            else:
                os.environ["CLAUDE_WORKSPACE_ROOT"] = prev

    def test_scan_assets_expose_gate_and_run_targets(self):
        from lib.adapters.config.native_scan import scan_agent_assets

        with tempfile.TemporaryDirectory() as td:
            with _patch_vault():
                r = scan_agent_assets("hermes", "agent-a", td, data_dir="store", run_target="windows")
            self.assertIn("gate", r)
            self.assertTrue(r["gate"]["passed"])
            self.assertIn("run_targets", r)
            self.assertEqual(r["run_targets"], ["windows", "wsl", "linux", "docker"])
            # docker 端应为框架容器内根（hermes → /home/hermes/.hermes）
            docker_paths = {a["paths"]["docker"] for a in r["assets"]}
            self.assertTrue(any(p.startswith("/home/hermes/.hermes") for p in docker_paths))


if __name__ == "__main__":
    unittest.main()
