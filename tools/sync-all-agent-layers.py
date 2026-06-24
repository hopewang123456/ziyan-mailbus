#!/usr/bin/env python3
"""Sync L0–L2 layer skills to all framework workspaces."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.framework_skills import HERMES_PROFILE_AGENTS, hermes_sync_skills_dir  # noqa: E402

SYNC_TARGETS: list[tuple[str, str, list[str]]] = [
    ("opencode", "dali", ["python", "tools/sync_framework_workspace_skills.py", "dali"]),
    ("openclaw", "xiaoqi", ["python", "tools/sync_framework_workspace_skills.py", "xiaoqi"]),
    ("openclaw", "yige", ["python", "tools/sync_framework_workspace_skills.py", "yige"]),
    ("claude", "lingyun", ["python", "tools/sync-claude-agent-context.py", "lingyun"]),
    ("claude", "lingyan", ["python", "tools/sync-claude-agent-context.py", "lingyan"]),
]

CODEX_AGENTS = ("lingxiao", "lingjian")


def _default_target(agent: str) -> Path | None:
    ai = ROOT.parent
    if agent == "dali":
        return ai / "opencode" / "skills"
    if agent in ("xiaoqi", "yige"):
        return ai / "openclaw_space" / "skills"
    if agent in HERMES_PROFILE_AGENTS:
        return hermes_sync_skills_dir(agent, mail_root=ROOT)
    return None


def _sync_hermes_all(data_dir: str) -> int:
    rc = 0
    for agent in HERMES_PROFILE_AGENTS:
        target = hermes_sync_skills_dir(agent, mail_root=ROOT)
        target.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            str(ROOT / "tools" / "sync_framework_workspace_skills.py"),
            agent,
            str(target),
            "--data-dir",
            data_dir,
            "--symlink",
        ]
        print(f"[sync-all] hermes_profile/{agent} → {target}")
        r = subprocess.run(cmd, cwd=str(ROOT))
        if r.returncode != 0:
            rc = r.returncode
    return rc


def _sync_codex_all(data_dir: str) -> int:
    rc = 0
    for agent in CODEX_AGENTS:
        print(f"[sync-all] codex/{agent} (CODEX_HOME skills)")
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "sync_codex_agent_skills.py")],
            cwd=str(ROOT),
            env={**dict(__import__("os").environ), "DATA_DIR": data_dir, "CODEX_AGENT": agent},
        )
        if r.returncode != 0:
            rc = r.returncode
    return rc


def main() -> int:
    p = argparse.ArgumentParser(description="Sync L0–L2 skills to all workspaces")
    p.add_argument("--data-dir", default=str(ROOT / "store"))
    p.add_argument("--skip-claude", action="store_true")
    p.add_argument("--skip-hermes", action="store_true")
    p.add_argument("--skip-codex", action="store_true")
    args = p.parse_args()
    env = {**dict(**__import__("os").environ), "DATA_DIR": args.data_dir}
    rc = 0

    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "patch-skills-index-framework.py")],
        cwd=str(ROOT),
        check=False,
    )

    for kind, agent, cmd in SYNC_TARGETS:
        if args.skip_claude and kind == "claude":
            continue
        target = _default_target(agent)
        full_cmd = [sys.executable, str(ROOT / cmd[1])] + cmd[2:]
        if target and "sync_framework_workspace_skills" in cmd[1]:
            full_cmd.extend([str(target), "--data-dir", args.data_dir, "--symlink"])
        elif "sync-claude-agent-context" in cmd[1]:
            full_cmd.extend(["--data-dir", args.data_dir])
        print(f"[sync-all] {kind}/{agent} …")
        r = subprocess.run(full_cmd, cwd=str(ROOT), env=env)
        if r.returncode != 0:
            rc = r.returncode

    if not args.skip_hermes:
        rc = rc or _sync_hermes_all(args.data_dir)

    if not args.skip_codex:
        rc = rc or _sync_codex_all(args.data_dir)

    v = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "validate-agent-layers.py"), "--check"],
        cwd=str(ROOT),
    )
    return rc or v.returncode


if __name__ == "__main__":
    raise SystemExit(main())
