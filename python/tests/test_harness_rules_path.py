"""Wave6/7: harness.rules_path settings + resolver."""
from __future__ import annotations

import tempfile
from pathlib import Path

from lib.adapters.config.config_admin import EDITABLE_SECTIONS, get_section, patch_section
from lib.application.harness import resolve_harness_rules_path
from lib.infra.utils import json_write


def test_harness_is_editable_section():
    assert "harness" in EDITABLE_SECTIONS


def test_patch_harness_rules_path_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        json_write(str(Path(tmp) / "config.json"), {"harness": {"mode": "production"}})
        result, _restart = patch_section(tmp, "harness", {"rules_path": "E:/rules-sot"})
        assert result.get("section") == "harness"
        got = get_section(tmp, "harness")
        data = got.get("data") or {}
        assert data.get("rules_path") == "E:/rules-sot"
        assert resolve_harness_rules_path({"harness": data}) == "E:/rules-sot"


def test_resolve_harness_rules_path_default():
    from lib.infra.constants import MAILBUS_RULES_ROOT

    path = resolve_harness_rules_path({})
    assert path == str(MAILBUS_RULES_ROOT)
