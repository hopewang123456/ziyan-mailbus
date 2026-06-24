#!/usr/bin/env python3
"""交付链平台调整：zi-claude→lingyun，lingyan→claude_code。"""
from __future__ import annotations

import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "store", "config.json")
STORE = os.path.join(ROOT, "store")
INBOX = os.path.join(STORE, "inbox")


def _migrate_inbox(old_key: str, new_key: str) -> None:
    old_dir = os.path.join(INBOX, old_key)
    new_dir = os.path.join(INBOX, new_key)
    if old_key == new_key:
        return
    os.makedirs(new_dir, exist_ok=True)
    if os.path.isdir(old_dir):
        for name in os.listdir(old_dir):
            src = os.path.join(old_dir, name)
            dst = os.path.join(new_dir, name)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
        shutil.rmtree(old_dir, ignore_errors=True)
    inbox_file = os.path.join(new_dir, "inbox.json")
    if not os.path.isfile(inbox_file):
        with open(inbox_file, "w", encoding="utf-8") as f:
            json.dump({"agent": new_key, "messages": [], "has_unread": False}, f, ensure_ascii=False, indent=2)


def main() -> None:
    with open(CONFIG, encoding="utf-8") as f:
        d = json.load(f)

    agents = d.setdefault("agents", {})

    # zi-claude → lingyun
    if "zi-claude" in agents:
        agents["lingyun"] = agents.pop("zi-claude")
    lingyun = agents.setdefault("lingyun", {})
    lingyun.update({
        "name": "灵云",
        "role": "精细编码",
        "type": "claude_code",
        "models": lingyun.get("models") or ["minimax-m2"],
        "push": {"cwd": r"E:\ai_tools"},
        "push_timeout_seconds": lingyun.get("push_timeout_seconds") or 900,
        "max_concurrency": 1,
        "inbox": "E:/ai_tools/mail/store/inbox/lingyun/inbox.json",
        "claude": {
            "permission_mode": "acceptEdits",
        },
        "launch": {
            "template": "claude_host",
            "cli": {"kind": "shell"},
            "browser": {
                "kind": "claude_ttyd",
                "url": "http://127.0.0.1:{port}/",
                "web_port": "9260",
                "start_wait_seconds": 15,
            },
            "desktop": {"enabled": False},
            "launch_via_api": True,
            "has_browser": True,
        },
        "profile_paths": {
            "identity": "/mnt/e/ai_tools/mail/identities/lingyun.md",
        },
    })

    # lingyan → claude_code
    lingyan = agents.setdefault("lingyan", {})
    lingyan.update({
        "name": lingyan.get("name") or "灵验",
        "role": "测试验证",
        "type": "claude_code",
        "models": ["minimax-m2"],
        "push": {"cwd": r"E:\ai_tools"},
        "push_timeout_seconds": lingyan.get("push_timeout_seconds") or 600,
        "max_concurrency": 1,
        "cli_msg_max_chars": lingyan.get("cli_msg_max_chars") or 4000,
        "processing_stale_minutes": lingyan.get("processing_stale_minutes") or 90,
        "file_task_content_threshold": lingyan.get("file_task_content_threshold") or 800,
        "inbox": "E:/ai_tools/mail/store/inbox/lingyan/inbox.json",
        "claude": {
            "permission_mode": "dontAsk",
            "push_flags": '--allowedTools "Bash,Read,Glob,Grep"',
        },
        "launch": {
            "template": "claude_host",
            "cli": {"kind": "shell"},
            "browser": {
                "kind": "claude_ttyd",
                "url": "http://127.0.0.1:{port}/",
                "web_port": "9261",
            "soul": "",
            "skills_dirs": [],
        },
    })
    for stale in ("profile",):
        lingyan.pop(stale, None)

    mc = d.setdefault("mailbus_claude", {})
    for plat in ("windows", "linux"):
        block = mc.setdefault(plat, {})
        roots = dict(block.get("default_project_roots") or {})
        if "zi-claude" in roots:
            roots["lingyun"] = roots.pop("zi-claude")
        roots.setdefault("lingyun", r"E:\ai_tools" if plat == "windows" else "/mnt/e/ai_tools")
        roots.setdefault("lingyan", r"E:\ai_tools" if plat == "windows" else "/mnt/e/ai_tools")
        block["default_project_roots"] = roots

    at = d.setdefault("agent_types", {})
    models = at.setdefault("models", {})
    models.setdefault("minimax-m2", {"claude_code": "--model MiniMax-M2.7"})

    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    _migrate_inbox("zi-claude", "lingyun")
    _migrate_inbox("lingyan", "lingyan")
    print("migrated config + inbox")


if __name__ == "__main__":
    main()
