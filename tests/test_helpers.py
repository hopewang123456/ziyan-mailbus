"""Shared pytest/unittest fixtures — mirror config SoT when store/ is wiped."""
from __future__ import annotations

import json
import os
import shutil

from lib.infra.constants import MAILBUS_ROOT
from lib.adapters.config.init_store import (
    build_agents_from_registry,
    mirror_dispatch_seed,
    mirror_org_json,
    mirror_rule_schemas_to_store,
    mirror_workflows_to_store,
)
from lib.infra.utils import json_write


def seed_runtime_from_sot(tmp: str, *, extra_config: dict | None = None) -> None:
    """Populate tmp with org/workflows/schemas/dispatch from mail/config + mail/org."""
    mirror_org_json(tmp, mail_root=MAILBUS_ROOT)
    mirror_workflows_to_store(tmp, mail_root=MAILBUS_ROOT)
    mirror_rule_schemas_to_store(tmp, mail_root=MAILBUS_ROOT)
    mirror_dispatch_seed(tmp, mail_root=MAILBUS_ROOT)

    for sub in ("inbox/agent-i", "inbox/agent-g", "msg-files", "tasks", "leads"):
        os.makedirs(os.path.join(tmp, sub), exist_ok=True)

    json_write(os.path.join(tmp, "inbox", "agent-i", "inbox.json"), {"agent": "agent-i", "messages": []})
    json_write(os.path.join(tmp, "inbox", "agent-g", "inbox.json"), {"agent": "agent-g", "messages": []})
    json_write(
        os.path.join(tmp, "human-queue.json"),
        {"version": "1.0.0", "updated_at": "2026-06-18T00:00:00+08:00", "items": []},
    )

    cfg_path = os.path.join(tmp, "config.json")
    if os.path.isfile(cfg_path):
        cfg = json.load(open(cfg_path, encoding="utf-8"))
    else:
        cfg = {}
    cfg.setdefault("mailbus_internal_llm", {
        "enabled": False,
        "guardrails": {"await_plan_approval_tier_min": "L"},
    })
    cfg.setdefault("mailbus_intake_bridge", {
        "enabled": True,
        "auto_spawn_analyze": True,
        "auto_spawn_content": False,
        "auto_spawn_solution": False,
    })
    if extra_config:
        cfg.update(extra_config)
    if not cfg.get("agents"):
        cfg["agents"] = build_agents_from_registry(data_dir=tmp, mail_root=MAILBUS_ROOT)
    json_write(cfg_path, cfg)


def copy_store_subdir_if_present(tmp: str, sub: str) -> None:
    """Legacy helper: copy mail/store/{sub} when populated (else no-op)."""
    root = os.path.join(os.path.dirname(__file__), "..", "store")
    src = os.path.join(root, sub)
    dst = os.path.join(tmp, sub)
    if os.path.isdir(src) and os.listdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)


def load_pursue_intake_example() -> dict:
    for base in (
        os.path.join(os.path.dirname(__file__), "..", "examples"),
        os.path.join(os.path.dirname(__file__), "..", "store", "examples"),
    ):
        path = os.path.join(base, "order-intake.pursue.example.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("order-intake.pursue.example.json")


def load_golden_a2a_path(letter: str) -> dict:
    """加载 store/examples/golden-a2a-path-{a,b,c,d}.json。"""
    letter = letter.lower().strip()
    if letter not in "abcd":
        raise ValueError(f"golden path must be a-d, got {letter!r}")
    name = f"golden-a2a-path-{letter}.json"
    for base in (
        os.path.join(os.path.dirname(__file__), "..", "store", "examples"),
        os.path.join(os.path.dirname(__file__), "..", "examples"),
    ):
        path = os.path.join(base, name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(name)


def seed_a2a_harness(tmp: str, *, mode: str = "stub", extra_config: dict | None = None) -> None:
    """seed_runtime_from_sot + harness/transport 默认 stub 配置。"""
    cfg = {
        "harness": {
            "mode": mode,
            "stub_fixtures_dir": "tests/fixtures/harness_stub",
        },
        "transport": {
            "channel_order": ["a2a_standard", "file_bus"],
            "a2a": {"max_retries": 3, "retry_backoff_sec": [2, 5, 10]},
        },
    }
    if extra_config:
        for k, v in extra_config.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k] = {**cfg[k], **v}
            else:
                cfg[k] = v
    seed_runtime_from_sot(tmp, extra_config=cfg)
    os.makedirs(os.path.join(tmp, "errors"), exist_ok=True)
