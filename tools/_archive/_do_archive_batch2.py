#!/usr/bin/env python3
"""P6-C01 batch 2: move zero/low-ref tools to _archive/."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "_archive"

KEEP = {
    "init-store.py", "write_reorg_risks.py", "validate-agent-layers.py",
    "validate-order-intake.py", "validate-workflows.py", "validate-scheduler.py",
    "validate-examples.py", "check-preflight.py", "sync-all-agent-layers.py",
    "sync-claude-agent-context.py", "sync_framework_workspace_skills.py",
    "sync_codex_agent_skills.py", "generate-compose-volumes.py",
    "live-dali-opencode-e2e.py", "verify-live-dali-e2e.py",
    "collect-pipeline-postmortem.py", "restart-mailbus.py",
    "patch-skills-index-framework.py", "resolve-agent-cli.py", "bootstrap-role-specs.py",
    "platform-scout.py", "pipeline-watchdog.py", "repair-pipeline-stuck.py",
    "pipeline-e2e-regression.py", "run-game-lvup-e2e.py", "test-automation-e2e.py",
    "triage-tasks.py", "flush-pending-audits.py", "complete-round2-regression.py",
    "pipeline-push-step1.py", "task-create-envelope.py", "watch-task-pipeline.py",
    "setup-internal-llm.py", "check-agentmemory-persistence.py", "sync-team-rules.py",
    "smoke-agent-disk-write.py", "validate-agents-config.py", "smoke-hermes-profiles.py",
    "smoke-codex-agent.py", "sync-codex-agent-skills.sh", "sync-openclaw-framework-skill.sh",
    "sync-hermes-framework-skill.sh", "sync-opencode-framework-skill.sh", "start-claude-web.sh",
    "launch-claude-cli.py", "launch-claude-browser.py", "launch-agent-desktop.py",
    "ensure-comfyui.py", "smoke-comfyui-gpu.py", "sync-comfyui-url.py", "sync-comfyui-url.ps1",
    "sync-n8n-url.py", "sync-n8n-url.ps1", "setup-n8n.ps1", "setup-n8n.sh",
    "ensure-n8n-publish-workflow.py", "run-final-acceptance.py", "set-primary-task.py",
    "reassign-pipeline-step.py", "prepare-game-courier.py", "game-courier-status.py",
    "poll-mini-step2.py", "smoke-platform-scout.py", "test-video-publish-drill.py",
    "smoke-dashboard-api.py", "external-tools-cli.py", "smoke-pipeline-mini.py",
    "archive-inbox-backlog.py",
    "_do_archive_batch2.py",
}

ARCHIVE.mkdir(exist_ok=True)
moved = []
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
print("--- remaining ---")
for r in remaining:
    print(r)
