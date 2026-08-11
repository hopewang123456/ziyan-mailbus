#!/usr/bin/env python3
"""Sync L0–L2 layer skills to all framework workspaces (v3: access/**/agent.json SoT)."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.adapters.config.agent_registry import load_all_agents  # noqa: E402
from lib.adapters.config.init_store import mirror_dispatch_seed, mirror_workflows_to_store  # noqa: E402
from lib.adapters.config.sync_layers import (  # noqa: E402
    default_use_symlink,
    iter_syncable_agents,
    mirror_rules_to_store,
)


def _sync_framework_workspace(
    agent: str,
    target: Path,
    data_dir: str,
    *,
    use_symlink: bool,
) -> int:
    target.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "sync_framework_workspace_skills.py"),
        agent,
        str(target),
        "--data-dir",
        data_dir,
    ]
    if use_symlink:
        cmd.append("--symlink")
    else:
        cmd.append("--copy")
    print(f"[sync-all] workspace/{agent} → {target}")
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def _sync_claude(agent: str, data_dir: str) -> int:
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "sync-claude-agent-context.py"),
        agent,
        "--data-dir",
        data_dir,
    ]
    print(f"[sync-all] claude_code/{agent} …")
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def _sync_codex(agent: str, data_dir: str) -> int:
    print(f"[sync-all] codex/{agent} (CODEX_HOME skills)")
    env = {**os.environ, "DATA_DIR": data_dir, "CODEX_AGENT": agent}
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "sync_codex_agent_skills.py")],
        cwd=str(ROOT),
        env=env,
    ).returncode


def main() -> int:
    p = argparse.ArgumentParser(description="Sync L0–L2 skills to all workspaces (registry SoT)")
    p.add_argument("--data-dir", default=str(ROOT / "store"))
    p.add_argument("--skip-claude", action="store_true")
    p.add_argument("--skip-hermes", action="store_true")
    p.add_argument("--skip-codex", action="store_true")
    p.add_argument("--skip-rules", action="store_true", help="skip mail/rules → store/rules mirror")
    p.add_argument(
        "--symlink",
        action="store_true",
        help="symlink skills (default: copy on Windows, symlink elsewhere)",
    )
    p.add_argument("--copy", action="store_true", help="force copy instead of symlink")
    args = p.parse_args()

    use_symlink = args.symlink and not args.copy
    if not args.symlink and not args.copy:
        use_symlink = default_use_symlink()

    rc = 0

    # skills-index from agent.json
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "patch-skills-index-framework.py")],
        cwd=str(ROOT),
    )
    if r.returncode != 0:
        rc = r.returncode

    if not args.skip_rules:
        copied = mirror_rules_to_store(args.data_dir, mail_root=ROOT)
        print(f"[sync-all] rules mirror → store/rules ({len(copied)} files)")
        wf = mirror_workflows_to_store(args.data_dir, mail_root=ROOT)
        if wf:
            print(f"[sync-all] workflows mirror → store/workflows ({', '.join(wf)})")
        disp = mirror_dispatch_seed(args.data_dir, mail_root=ROOT)
        if disp:
            print(f"[sync-all] dispatch mirror → store/dispatch ({', '.join(disp)})")

    agents = load_all_agents(mail_root=ROOT, refresh=True)
    if len(agents) != 13:
        print(f"[sync-all] WARN: expected 13 agents, got {len(agents)}", file=sys.stderr)

    for agent_id, fw, target in iter_syncable_agents(mail_root=ROOT):
        if args.skip_hermes and fw == "hermes_profile":
            continue
        if args.skip_codex and fw == "codex":
            continue
        if args.skip_claude and fw == "claude_code":
            continue

        if fw == "claude_code":
            rc = rc or _sync_claude(agent_id, args.data_dir)
        elif fw == "codex":
            rc = rc or _sync_codex(agent_id, args.data_dir)
        elif target is not None:
            rc = rc or _sync_framework_workspace(
                agent_id, target, args.data_dir, use_symlink=use_symlink
            )
        else:
            print(f"[sync-all] skip {agent_id} ({fw}): no sync target", file=sys.stderr)

    v = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "validate-agent-layers.py"), "--check"],
        cwd=str(ROOT),
    )
    return rc or v.returncode


if __name__ == "__main__":
    raise SystemExit(main())
