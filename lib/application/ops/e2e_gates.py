"""Product L-gates E2E use-cases (Wave C) — fixture store only, no cloud keys."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

from lib.adapters.frameworks.support import assert_spawn_argv_allowed
from lib.adapters.results.ack import ack_message, list_unacked
from lib.application.transport_send import send_outbound
from lib.desktop_launch import merge_launch_desktop
from lib.harness.contract import write_d1_step_result
from lib.model_router import is_no_llm_notice
from lib.scan.inbox import finalize_auto_ack
from lib.utils import json_read, json_write


def _ensure_fixture_store(data_dir: str) -> Path:
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    cfg = root / "config.json"
    if not cfg.is_file():
        cfg.write_text(
            json.dumps(
                {
                    "agents": {
                        "e2e_agent": {
                            "type": "none",
                            "enabled": True,
                            "launch": {
                                "template": "codex_docker",
                                "desktop": {
                                    "enabled": True,
                                    "kind": "codex_desktop",
                                    "gateway_port": 9220,
                                },
                            },
                        }
                    },
                    "agent_types": {
                        "launch_templates": {
                            "codex_docker": {
                                "desktop": {"kind": "codex_desktop", "enabled": True}
                            }
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    (root / "tasks").mkdir(exist_ok=True)
    (root / "msg-results").mkdir(exist_ok=True)
    (root / "inbox").mkdir(exist_ok=True)
    return root


def run_l_inbox(data_dir: str) -> dict[str, Any]:
    """L-inbox: deliver → inbox visible → ack observable."""
    _ensure_fixture_store(data_dir)
    agent = "e2e_agent"
    msg_id = "e2e-inbox-001"
    out = send_outbound(
        data_dir,
        agent_id=agent,
        msg_id=msg_id,
        intent="e2e inbox delivery",
        channel="file_bus",
        extra_headers={"msg_type": "task", "from_agent": "mailbus"},
    )
    if not out.get("ok"):
        return {"ok": False, "gate": "L-inbox", "stage": "deliver", "detail": out}

    inbox_path = Path(data_dir) / "inbox" / agent / "inbox.json"
    inbox = json.loads(inbox_path.read_text(encoding="utf-8"))
    msgs = inbox.get("messages") or []
    found = next((m for m in msgs if m.get("id") == msg_id), None)
    if not found:
        return {"ok": False, "gate": "L-inbox", "stage": "visible", "detail": "msg missing"}

    ack_message(data_dir, agent, msg_id)
    unacked = list_unacked(data_dir, agent, [msg_id])
    ack_data = json_read(str(Path(data_dir) / "inbox" / agent / "ack.json"), [])
    acked = any(
        isinstance(a, dict) and a.get("msg_id") == msg_id and a.get("action") == "ack"
        for a in (ack_data if isinstance(ack_data, list) else [])
    )
    ok = (not unacked) and acked and found.get("state") == "pending"
    return {
        "ok": ok,
        "gate": "L-inbox",
        "msg_id": msg_id,
        "inbox_visible": True,
        "acked": acked,
        "unacked": unacked,
        "state": found.get("state"),
    }


def run_l_pipeline(data_dir: str) -> dict[str, Any]:
    """L-pipeline: multi-step + D1 msg-results/step on disk (fixture write)."""
    _ensure_fixture_store(data_dir)
    task_id = "e2e-pipe-001"
    agent = "e2e_agent"
    steps = ("s1", "s2")
    paths: list[str] = []

    task_path = Path(data_dir) / "tasks" / f"{task_id}.json"
    json_write(
        str(task_path),
        {
            "task_id": task_id,
            "status": "running",
            "assignee": agent,
            "chain": [{"step_id": s, "to_person": agent} for s in steps],
        },
    )

    for sid in steps:
        send_outbound(
            data_dir,
            agent_id=agent,
            msg_id=f"msg-{task_id}-{sid}",
            intent=f"pipeline step {sid}",
            channel="file_bus",
            task_id=task_id,
            step_id=sid,
            extra_headers={"msg_type": "task", "from_agent": "mailbus"},
        )
        p = write_d1_step_result(
            data_dir,
            task_id,
            sid,
            status="done",
            summary=f"e2e step {sid}",
            agent_id=agent,
            contract_id=f"c-{sid}",
        )
        paths.append(p)

    ok_files = all(os.path.isfile(p) for p in paths)
    bodies = []
    for p in paths:
        body = json.loads(Path(p).read_text(encoding="utf-8"))
        bodies.append(body)
        if body.get("schema") != "mailbus-step-result-v1":
            ok_files = False

    return {
        "ok": ok_files and len(paths) == 2,
        "gate": "L-pipeline",
        "task_id": task_id,
        "steps": list(steps),
        "paths": paths,
        "statuses": [b.get("status") for b in bodies],
    }


def run_l_notice(data_dir: str) -> dict[str, Any]:
    """L-notice: notice route + auto ack without LLM."""
    _ensure_fixture_store(data_dir)
    agent = "e2e_agent"
    msg_id = "remind-e2e-notice-001"
    out = send_outbound(
        data_dir,
        agent_id=agent,
        msg_id=msg_id,
        intent="【系统通知】e2e notice digest — no LLM",
        channel="file_bus",
        extra_headers={"msg_type": "notice", "from_agent": "mailbus"},
    )
    if not out.get("ok"):
        return {"ok": False, "gate": "L-notice", "stage": "deliver", "detail": out}

    inbox_path = Path(data_dir) / "inbox" / agent / "inbox.json"
    inbox = json.loads(inbox_path.read_text(encoding="utf-8"))
    entry = next(m for m in inbox["messages"] if m.get("id") == msg_id)
    no_llm = is_no_llm_notice(entry)
    if not no_llm:
        return {"ok": False, "gate": "L-notice", "stage": "route", "detail": "expected no_llm"}

    finalize_auto_ack(data_dir, agent, msg_id, entry)
    inbox2 = json.loads(inbox_path.read_text(encoding="utf-8"))
    after = next(m for m in inbox2["messages"] if m.get("id") == msg_id)
    state = after.get("state") or after.get("status")
    ok = state in ("done", "acknowledged") or after.get("done_note", "").startswith("auto:")
    return {
        "ok": bool(ok),
        "gate": "L-notice",
        "msg_id": msg_id,
        "no_llm": no_llm,
        "state": state,
        "done_note": after.get("done_note"),
    }


def run_l_desktop(data_dir: str) -> dict[str, Any]:
    """L-desktop: launch config merge + argv whitelist probe (mock spawn, no GUI)."""
    _ensure_fixture_store(data_dir)
    cfg = json_read(str(Path(data_dir) / "config.json"), {})
    agent_cfg = (cfg.get("agents") or {}).get("e2e_agent") or {}
    types = cfg.get("agent_types") or {}
    merged = merge_launch_desktop(agent_cfg, types)
    merge_ok = merged.get("kind") == "codex_desktop" and int(merged.get("gateway_port") or 0) == 9220

    # Representative desktop-related argv (not shell wrappers).
    argv = ["python", "-c", "print('e2e-desktop-probe')"]
    assert_spawn_argv_allowed(argv, cfg)

    banned_ok = False
    try:
        assert_spawn_argv_allowed(["powershell.exe", "-Command", "echo x"], cfg)
    except Exception:
        banned_ok = True

    recorded: dict[str, Any] = {}

    def _fake_popen(cmd, *args, **kwargs):
        recorded["argv"] = list(cmd) if not isinstance(cmd, str) else [cmd]
        recorded["shell"] = bool(kwargs.get("shell", False))
        recorded["args"] = args
        recorded["kwargs"] = {k: v for k, v in kwargs.items() if k != "env"}

        class _Proc:
            pid = 4242
            returncode = 0

            def wait(self, timeout=None):
                return 0

            def communicate(self, input=None, timeout=None):
                return (b"", b"")

        return _Proc()

    with patch("subprocess.Popen", side_effect=_fake_popen):
        import subprocess

        # Explicit shell=False — L-desktop forbids shell=True spawns.
        subprocess.Popen(argv, shell=False)

    spawn_ok = (
        recorded.get("argv") == argv
        and recorded.get("shell") is False
        and "shell" in recorded
    )
    ok = bool(merge_ok and banned_ok and spawn_ok)
    return {
        "ok": ok,
        "gate": "L-desktop",
        "merged": merged,
        "merge_ok": merge_ok,
        "argv": argv,
        "banned_shell_wrapper": banned_ok,
        "spawn_shell": recorded.get("shell"),
        "spawn_argv": recorded.get("argv"),
    }


def run_all_gates(data_dir: str) -> dict[str, Any]:
    """Run all four product gates against a fixture data_dir."""
    _ensure_fixture_store(data_dir)
    results = [
        run_l_inbox(data_dir),
        run_l_pipeline(data_dir),
        run_l_notice(data_dir),
        run_l_desktop(data_dir),
    ]
    return {
        "ok": all(r.get("ok") for r in results),
        "gates": {r["gate"]: r for r in results},
    }
