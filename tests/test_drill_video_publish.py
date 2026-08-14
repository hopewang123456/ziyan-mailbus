"""Wave7: video_publish drill helpers (dry / fixture-backed)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from tests.test_helpers import seed_runtime_from_sot

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vault"
EXTERNAL_TOOLS = FIXTURES / "external-tools"


def test_import_video_publish():
    from lib.application.workflow.drill import video_publish as vp

    assert hasattr(vp, "run_video_publish_drill")
    assert hasattr(vp, "probe_n8n_webhook")


def test_probe_n8n_empty_url():
    from lib.application.workflow.drill.video_publish import probe_n8n_webhook

    got = probe_n8n_webhook("")
    assert got.get("ok") is False
    assert "empty" in str(got.get("detail", "")).lower() or got.get("url") == ""


def test_run_drill_dry_with_fixtures():
    from lib.application.workflow.drill.video_publish import DrillError, run_video_publish_drill

    with tempfile.TemporaryDirectory() as tmp:
        seed_runtime_from_sot(
            tmp,
            extra_config={
                "mailbus_workflow": {"tool_live": False, "tool_live_gates": ["publish_go"]},
            },
        )
        with mock.patch.dict(os.environ, {"MAILBUS_EXTERNAL_TOOLS_DIR": str(EXTERNAL_TOOLS)}, clear=False):
            try:
                result = run_video_publish_drill(tmp, mode="dry", live=False)
            except DrillError as exc:
                pytest.fail(f"unexpected DrillError: {exc.code} {exc.message}")
            except Exception as exc:
                pytest.fail(f"drill raised: {exc}")
        assert isinstance(result, dict)
        assert result.get("ok") is True
        assert "steps" in result


def test_check_n8n_mode_without_env():
    from lib.application.workflow.drill.video_publish import run_video_publish_drill

    env = os.environ.copy()
    env.pop("N8N_PUBLISH_WEBHOOK_URL", None)
    with mock.patch.dict(os.environ, env, clear=True):
        os.environ.pop("N8N_PUBLISH_WEBHOOK_URL", None)
        result = run_video_publish_drill("store", mode="check-n8n")
        assert result.get("mode") == "check-n8n"
        assert result.get("ok") is False
