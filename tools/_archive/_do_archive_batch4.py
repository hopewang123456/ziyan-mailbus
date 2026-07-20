#!/usr/bin/env python3
"""P6-C01 batch 4: slim tools/ root to ~30."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "_archive"

KEEP = {
    "mailbus.py",
    "ollama-wsl-proxy.py",
    "ensure-ollama.py",
    "init-store.py",
    "mailbus-store-cleanup.py",
    "patch-skills-index-framework.py",
    "sync-all-agent-layers.py",
    "sync-claude-agent-context.py",
    "sync_codex_agent_skills.py",
    "sync-codex-agent-skills.sh",
    "sync-codex-desktop-config.py",
    "sync-hermes-framework-skill.sh",
    "sync-openclaw-framework-skill.sh",
    "sync-opencode-framework-skill.sh",
    "sync-team-rules.py",
    "start-claude-web.sh",
    "resolve-agent-cli.py",
    "launch-claude-cli.py",
    "launch-claude-browser.py",
    "launch-agent-desktop.py",
    "validate-agent-layers.py",
    "validate-agents-config.py",
    "validate-examples.py",
    "generate-compose-volumes.py",
    "platform-scout.py",
    "pipeline-watchdog.py",
    "repair-pipeline-stuck.py",
    "smoke-codex-agent.py",
    "smoke-agent-disk-write.py",
    "smoke-hermes-profiles.py",
    "_do_archive_batch4.py",
}

ARCHIVE.mkdir(exist_ok=True)
moved: list[str] = []
for f in sorted(ROOT.iterdir()):
    if not f.is_file():
        continue
    if f.name in KEEP:
        continue
    dest = ARCHIVE / f.name
    if dest.exists():
        print(f"skip exists: {f.name}")
        continue
    shutil.move(str(f), str(dest))
    moved.append(f.name)

remaining = sorted(x.name for x in ROOT.iterdir() if x.is_file())
print(f"moved={len(moved)} remaining={len(remaining)}")
for m in moved:
    print(f"  -> _archive/{m}")
