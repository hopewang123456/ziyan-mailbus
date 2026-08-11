"""Wave C — product four-gate E2E (fixture store, no cloud keys)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.application.ops.e2e_gates import (
    run_all_gates,
    run_l_desktop,
    run_l_inbox,
    run_l_notice,
    run_l_pipeline,
)


@pytest.fixture
def e2e_store(tmp_path: Path) -> str:
    """Isolated fixture store — never touch repo store/."""
    return str(tmp_path)


class TestLInbox:
    def test_deliver_visible_ack(self, e2e_store: str):
        r = run_l_inbox(e2e_store)
        assert r["ok"], r
        assert r["inbox_visible"] is True
        assert r["acked"] is True
        assert r["unacked"] == []
        inbox = json.loads(
            Path(e2e_store, "inbox", "e2e_agent", "inbox.json").read_text(encoding="utf-8")
        )
        assert any(m.get("id") == r["msg_id"] for m in inbox["messages"])


class TestLPipeline:
    def test_multi_step_d1_msg_results(self, e2e_store: str):
        r = run_l_pipeline(e2e_store)
        assert r["ok"], r
        assert r["steps"] == ["s1", "s2"]
        assert r["statuses"] == ["done", "done"]
        for sid in ("s1", "s2"):
            p = Path(e2e_store, "msg-results", r["task_id"], f"step-{sid}.json")
            assert p.is_file()
            body = json.loads(p.read_text(encoding="utf-8"))
            assert body["schema"] == "mailbus-step-result-v1"
            assert body["step_id"] == sid


class TestLNotice:
    def test_notice_auto_ack_no_llm(self, e2e_store: str):
        r = run_l_notice(e2e_store)
        assert r["ok"], r
        assert r["no_llm"] is True
        assert r["state"] in ("done", "acknowledged") or str(r.get("done_note", "")).startswith(
            "auto:"
        )


class TestLDesktop:
    def test_merge_and_mock_spawn_argv(self, e2e_store: str):
        r = run_l_desktop(e2e_store)
        assert r["ok"], r
        assert r["merge_ok"] is True
        assert r["merged"]["kind"] == "codex_desktop"
        assert r["banned_shell_wrapper"] is True
        assert r["spawn_shell"] is False
        assert r["spawn_argv"][0] == "python"


class TestAllGates:
    def test_run_all(self, e2e_store: str):
        r = run_all_gates(e2e_store)
        assert r["ok"], r
        assert set(r["gates"]) == {"L-inbox", "L-pipeline", "L-notice", "L-desktop"}
