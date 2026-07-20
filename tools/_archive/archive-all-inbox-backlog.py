#!/usr/bin/env python3
"""批量归档各 agent inbox 历史积压。"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.utils import json_read, resolve_paths


def _load_archive_fn():
    path = os.path.join(os.path.dirname(__file__), "archive-inbox-backlog.py")
    spec = importlib.util.spec_from_file_location("archive_inbox_backlog", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod.archive_inbox_backlog


def _agents(data_dir: str) -> list[str]:
    paths = resolve_paths(data_dir)
    inbox_root = paths["inbox"]
    if not os.path.isdir(inbox_root):
        return []
    out: list[str] = []
    for name in sorted(os.listdir(inbox_root)):
        if os.path.isfile(os.path.join(inbox_root, name, "inbox.json")):
            out.append(name)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Archive inbox backlog for all agents")
    p.add_argument("--data-dir", default=os.environ.get("MAILBUS_DATA", "store"))
    p.add_argument("--older-than-days", type=int, default=7)
    p.add_argument("--keep-recent", type=int, default=30)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--agent", action="append", default=[], help="limit to agent(s)")
    args = p.parse_args()
    data_dir = os.path.abspath(args.data_dir)
    agents = args.agent or _agents(data_dir)
    if not agents:
        print("[archive-all] no agents found")
        return 1

    archive_inbox_backlog = _load_archive_fn()
    total_archived = 0
    for agent in agents:
        inbox_path = f"{resolve_paths(data_dir)['inbox']}/{agent}/inbox.json"
        if not os.path.isfile(inbox_path):
            continue
        try:
            before = len(json_read(inbox_path, {}).get("messages", []))
        except OSError as exc:
            print(f"  {agent}: skip ({exc})")
            continue
        out = archive_inbox_backlog(
            data_dir,
            agent,
            older_than_days=args.older_than_days,
            keep_recent=args.keep_recent,
            dry_run=args.dry_run,
        )
        key = "would_archive" if args.dry_run else "archived"
        n = int(out.get(key, 0))
        total_archived += n
        after = before - n if not args.dry_run else before
        print(f"  {agent}: before={before} {key}={n} after~={after}")

    label = "would_archive" if args.dry_run else "archived"
    print(f"[archive-all] {label}={total_archived} across {len(agents)} agents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
