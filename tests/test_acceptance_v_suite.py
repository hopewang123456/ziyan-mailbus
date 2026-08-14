"""§16.3 post-cleanup acceptance checks (automatable subset).

Legacy package paths (`lib/ports`, `lib/transport`, `lib/agent_adapters`) are gone;
this suite asserts the replacement layout (interfaces / core / adapters).
"""
from __future__ import annotations

import ast
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib"
TOOLS = ROOT / "tools"
APP = LIB / "application"

# Deleted / relocated modules — production code must not import these paths.
_FORBIDDEN_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+lib\.(?:agent_adapters|scanner)\b",
    re.M,
)
_CONCRETE_FW_RE = re.compile(
    r"from\s+lib\.adapters\.frameworks(?:\.registry)?\s+import\s+[^\n]*"
    r"(?:OpenClaw|Codex|Hermes|Cline|OpenCode|ClaudeCode|Cursor)Adapter"
    r"|import\s+lib\.adapters\.frameworks\.registry\s+as\s+",
)
_PUSHER_PRIVATE_RE = re.compile(r"pusher\._\w+")


def _iter_py(root: Path):
    if not root.is_dir():
        return
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        yield p


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


class TestAcceptanceVSuite(unittest.TestCase):
    def test_no_deleted_module_imports_in_lib_tools(self):
        """No imports of deleted modules (agent_adapters, scanner) under lib/ + tools/."""
        hits = []
        for base in (LIB, TOOLS):
            for p in _iter_py(base):
                text = _read(p)
                if _FORBIDDEN_IMPORT_RE.search(text):
                    hits.append(str(p.relative_to(ROOT)))
                # relative leftovers from move
                if re.search(r"from\s+\.agent_adapters\s+import", text):
                    hits.append(f"{p.relative_to(ROOT)}:.agent_adapters")
        self.assertEqual(hits, [], msg=f"deleted module imports: {hits}")

    def test_production_harness_no_pusher_private(self):
        """ProductionHarness must not call pusher._* privates."""
        path = APP / "harness" / "production.py"
        self.assertTrue(path.is_file())
        text = _read(path)
        self.assertIsNone(_PUSHER_PRIVATE_RE.search(text), "pusher._* still referenced")

    def test_application_no_concrete_framework_adapters(self):
        """application must not import concrete *Adapter classes."""
        hits = []
        for p in _iter_py(APP):
            text = _read(p)
            if _CONCRETE_FW_RE.search(text):
                hits.append(str(p.relative_to(ROOT)))
            # bare class imports from frameworks package
            if re.search(
                r"from\s+lib\.adapters\.frameworks\s+import\s+[^\n]*Adapter",
                text,
            ):
                # allow non-concrete helpers only — flag *Adapter
                for m in re.finditer(
                    r"from\s+lib\.adapters\.frameworks\s+import\s+([^\n]+)",
                    text,
                ):
                    names = m.group(1)
                    if re.search(r"\b\w+Adapter\b", names) and "BaseAdapter" not in names.replace(
                        "BaseAdapter", ""
                    ):
                        # BaseAdapter alone ok; concrete *Adapter not
                        concrete = [
                            n.strip()
                            for n in names.split(",")
                            if n.strip().endswith("Adapter") and n.strip() != "BaseAdapter"
                        ]
                        if concrete:
                            hits.append(f"{p.relative_to(ROOT)}:{concrete}")
        self.assertEqual(hits, [], msg=f"concrete framework imports: {hits}")

    def test_loopback_write_without_token(self):
        """Loopback may write without token; forged non-loopback without token is denied."""
        from lib.application.mailbus_token import authorize_write, ensure_token
        from lib.domain.types import AuthDecision, ClientContext

        with tempfile.TemporaryDirectory() as td:
            ensure_token(td)
            self.assertEqual(
                authorize_write(td, ClientContext(remote_addr="127.0.0.1")),
                AuthDecision.ALLOW,
            )
            self.assertEqual(
                authorize_write(td, ClientContext(remote_addr="192.168.1.10")),
                AuthDecision.DENY,
            )

    def test_rotate_invalidates_old_token(self):
        """rotate: remote without token denied; after rotate old Bearer fails."""
        from lib.application.mailbus_token import authorize_write, ensure_token, rotate_token
        from lib.domain.types import AuthDecision, ClientContext

        with tempfile.TemporaryDirectory() as td:
            old = ensure_token(td)
            denied = rotate_token(td, ClientContext(remote_addr="10.0.0.2"))
            self.assertFalse(denied.get("ok"))
            ok = rotate_token(
                td, ClientContext(remote_addr="10.0.0.2", authorization=f"Bearer {old}")
            )
            self.assertTrue(ok.get("ok"))
            new = ok["token"]
            self.assertNotEqual(new, old)
            self.assertEqual(
                authorize_write(
                    td, ClientContext(remote_addr="10.0.0.2", authorization=f"Bearer {old}")
                ),
                AuthDecision.DENY,
            )
            self.assertEqual(
                authorize_write(
                    td, ClientContext(remote_addr="10.0.0.2", authorization=f"Bearer {new}")
                ),
                AuthDecision.ALLOW,
            )

    def test_enable_rollback_contract(self):
        """enable mid-failure leaves no half-finished plane — mocked fixture (no Docker)."""
        from tests.test_v6_enable_rollback import run_enable_probe_fail_no_half_finished

        with tempfile.TemporaryDirectory() as td:
            Path(td, "config.json").write_text(
                '{"frameworks": {}, "agents": {"mailbus": {"type": "hermes", "enabled": true}}}',
                encoding="utf-8",
            )
            run_enable_probe_fail_no_half_finished(td)

    def test_json_write_uses_file_lock(self):
        """json_write / config RMW use file_lock."""
        utils = _read(LIB / "infra" / "utils.py")
        # locate json_write body roughly
        self.assertIn("def json_write", utils)
        idx = utils.index("def json_write")
        chunk = utils[idx : idx + 800]
        self.assertIn("file_lock", chunk)
        repo = LIB / "adapters" / "config" / "file_repo.py"
        self.assertTrue(repo.is_file())
        self.assertIn("file_lock", _read(repo))

    def test_align_smoke(self):
        """align_store_from_registry smoke (temp store, expect_min=0)."""
        from lib.application.align_store import align_store_from_registry

        with tempfile.TemporaryDirectory() as td:
            Path(td, "config.json").write_text('{"agents": {}}', encoding="utf-8")
            out = align_store_from_registry(td, expect_min=0)
            self.assertIn("ok", out)

    def test_harness_import_smoke(self):
        """Harness + scan imports remain wired after package moves."""
        from lib.application.harness.production import ProductionHarness
        from lib.application.scan import scan_all

        self.assertTrue(callable(ProductionHarness))
        self.assertTrue(callable(scan_all))

    def test_gitignore_secrets(self):
        """.gitignore must ignore store/secrets.json."""
        gi = _read(ROOT / ".gitignore")
        self.assertIn("store/secrets.json", gi)

    def test_skill_ids_contract_not_tree_scan(self):
        """Skill ids enter the contract; adapters must not rglob a skills tree."""
        push = _read(LIB / "application" / "push_with_contract.py")
        self.assertIn("domain_skill_ids", push)
        contract = _read(LIB / "application" / "harness" / "contract.py")
        self.assertIn("domain_skill_ids", contract)
        # adapters/frameworks must not rglob a skills tree
        bad = []
        for p in _iter_py(LIB / "adapters" / "frameworks"):
            text = _read(p)
            if re.search(r"rglob\([^\)]*skill", text, re.I) or "os.walk" in text and "skill" in text.lower():
                bad.append(str(p.relative_to(ROOT)))
        self.assertEqual(bad, [], msg=f"skill tree scan: {bad}")

    def test_desktop_launchers_no_lib_import(self):
        """Desktop / tools/mailbus launchers must not import lib internals."""
        launchers = list((TOOLS / "mailbus").glob("*.bat")) if (TOOLS / "mailbus").is_dir() else []
        desk = Path.home() / "Desktop"
        if desk.is_dir():
            for p in desk.iterdir():
                if p.is_dir() and ("AI" in p.name or p.name.startswith("mailbus")):
                    launchers.extend(p.glob("*.bat"))
        if not launchers:
            self.skipTest("no desktop/tools/mailbus *.bat found")
        bad = []
        for bat in launchers:
            text = _read(bat)
            if re.search(r"from\s+lib\.|import\s+lib\.|python\s+-c\s+[\"'].*lib\.", text):
                bad.append(str(bat))
            if "agent_adapters" in text or "lib.application.scan" in text:
                bad.append(str(bat))
        self.assertEqual(bad, [], msg=f"legacy launcher imports: {bad}")


class TestFrameworkRegisterHook(unittest.TestCase):
    """register_framework entry-point smoke."""

    def test_register_fake_framework(self):
        from lib.adapters.frameworks import (
            BaseAdapter,
            get_adapter,
            register_framework,
            unregister_framework,
        )

        class FakeAdapter(BaseAdapter):
            def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None, **kw):
                return "echo fake"

        name = "_f6_fake_fw"
        unregister_framework(name)
        register_framework(name, FakeAdapter(), replace=True)
        try:
            self.assertIsInstance(get_adapter(name), FakeAdapter)
        finally:
            unregister_framework(name)
        self.assertIsNone(get_adapter(name))


class TestSettingsApiSurface(unittest.TestCase):
    """Cockpit settings / frameworks / integrations / token handlers exist."""

    def test_handlers_importable(self):
        from lib.api import handlers_lifecycle, handlers_settings, handlers_system

        for name in (
            "handle_settings_sections",
            "handle_settings_env_get",
            "handle_integrations",
        ):
            self.assertTrue(callable(getattr(handlers_settings, name)))
        self.assertTrue(callable(handlers_system.handle_frameworks))
        self.assertTrue(callable(handlers_lifecycle.handle_mailbus_token))
        self.assertTrue(callable(handlers_lifecycle.handle_framework_enable))

    def test_typed_overview_views(self):
        from lib.application.integrations_query import integrations_overview
        from lib.domain.types import IntegrationsOverviewView, SettingsSectionsView

        out = integrations_overview("/tmp")
        self.assertIn("integrations", out)
        self.assertIn("count", out)
        # TypedDict structural check
        _: IntegrationsOverviewView = out
        sections: SettingsSectionsView = {"status": "ok", "sections": ["env"]}
        self.assertEqual(sections["status"], "ok")


if __name__ == "__main__":
    unittest.main()
