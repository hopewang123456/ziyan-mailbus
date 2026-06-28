#!/usr/bin/env python3
"""One-shot: find tools root files safe to archive (no external refs)."""
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
files = sorted(f.name for f in root.iterdir() if f.is_file() and f.name != "_scan_archive.py")

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
}

candidates = [f for f in files if f not in KEEP]
safe: list[str] = []
blocked: dict[str, list[str]] = {}

for f in candidates:
    hits: list[str] = []
    for pat in (f"tools/{f}", f"/tools/{f}"):
        r = subprocess.run(
            [
                "rg", "-l", pat, "E:/ai_tools",
                "--glob", "!*venv*",
                "--glob", "!_archive/*",
                "--glob", "!_incidents/*",
            ],
            capture_output=True,
            text=True,
        )
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line or line.endswith(f"tools/{f}"):
                continue
            hits.append(line)
    if hits:
        blocked[f] = hits[:5]
    else:
        safe.append(f)

print(f"KEEP={len(KEEP)} root={len(files)} safe={len(safe)} blocked={len(blocked)}")
print("---SAFE---")
for s in safe:
    print(s)
print("---BLOCKED---")
for k, v in sorted(blocked.items()):
    print(f"{k} -> {v[:3]}")
