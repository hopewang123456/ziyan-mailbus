#!/usr/bin/env python3
"""Sync skills-index entries to a workspace skills directory (OpenCode / OpenClaw / etc.)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.framework_skills import sync_agent_skills_from_index  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Sync agent skills to workspace skills dir")
    p.add_argument("agent", help="agent id, e.g. dali, xiaoqi")
    p.add_argument("target", help="target skills root directory")
    p.add_argument("--data-dir", default=os.environ.get("DATA_DIR") or str(ROOT / "store"))
    p.add_argument("--symlink", action="store_true", help="symlink instead of copy")
    p.add_argument("--copy", action="store_true", help="copy files (container / read-only adapters)")
    args = p.parse_args()

    index_path = Path(args.data_dir) / "agents" / "json" / "skills-index.json"
    if not index_path.is_file():
        print(f"[sync-framework-workspace] no index: {index_path}", file=sys.stderr)
        return 0
    index = json.loads(index_path.read_text(encoding="utf-8"))
    target = Path(args.target)
    target.mkdir(parents=True, exist_ok=True)
    use_symlink = args.symlink and not args.copy
    installed = sync_agent_skills_from_index(
        args.agent,
        target,
        index,
        mail_root=ROOT,
        use_symlink=use_symlink,
    )
    print(f"[sync-framework-workspace] agent={args.agent} target={target} installed={len(installed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
