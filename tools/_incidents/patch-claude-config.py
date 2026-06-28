#!/usr/bin/env python3
"""One-shot patch: add mailbus_claude + zi-claude to store/config.json."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "store", "config.json")

with open(CONFIG, encoding="utf-8") as f:
    d = json.load(f)

d["mailbus_claude"] = {
    "platform": "auto",
    "windows": {
        "enabled": True,
        "claude_home": r"C:\Users\hopew\.claude",
        "claude_bin": "claude",
        "default_project_dir": r"E:\ai_tools",
        "default_project_roots": {"zi-claude": r"E:\ai_tools"},
    },
    "linux": {
        "enabled": False,
        "claude_home": "/home/administrator/.claude",
        "claude_bin": "claude",
        "default_project_dir": "/mnt/e/ai_tools",
        "default_project_roots": {"zi-claude": "/mnt/e/ai_tools"},
    },
}

at = d.setdefault("agent_types", {})
at["claude_code"] = {
    "push": "claude -p 'MSG'",
    "description": "Claude Code CLI（宿主机 headless，Windows/Linux 可选）",
}
lt = at.setdefault("launch_templates", {})
lt["claude_host"] = {
    "cli": {"kind": "shell", "start_wait_seconds": 0},
    "desktop": {"kind": "claude_interactive"},
}
models = at.setdefault("models", {})
models["minimax-m2"] = {"claude_code": "--model MiniMax-M2.7"}

d["agents"]["zi-claude"] = {
    "name": "子言-Claude",
    "role": "编码",
    "type": "claude_code",
    "models": ["minimax-m2"],
    "push": {"cwd": r"E:\ai_tools"},
    "push_timeout_seconds": 900,
    "inbox": "E:/ai_tools/mail/store/inbox/zi-claude/inbox.json",
    "launch": {
        "template": "claude_host",
        "cli": {"kind": "shell"},
        "desktop": {
            "enabled": True,
            "kind": "claude_interactive",
            "project_dir": r"E:\ai_tools",
        },
        "launch_via_api": True,
        "has_browser": False,
    },
    "profile_paths": {
        "identity": "/mnt/e/ai_tools/mail/identities/zi-claude.md",
    },
}

with open(CONFIG, "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print("patched", CONFIG)
