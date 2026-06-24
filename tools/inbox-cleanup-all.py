#!/usr/bin/env python3
"""inbox 积压统计 + 清理（prune notice + stale remind + 归档）。"""
import os
import sys
from collections import Counter

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MAIL)

from lib.commands import load_config
from lib.models import Inbox, MsgStatus
from lib.utils import json_read, resolve_paths


def inbox_stats(data_dir: str, agents: dict) -> dict:
    paths = resolve_paths(data_dir)
    out = {}
    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        data = json_read(inbox_file, {}, ttl=0)
        if not data:
            continue
        inbox = Inbox.from_dict(data)
        states = Counter()
        pending = 0
        for m in inbox.messages:
            st = (
                inbox.msg_field(m, "state", "")
                or inbox.msg_field(m, "status", "")
                or "?"
            ).lower()
            states[st] += 1
            if st in (MsgStatus.PENDING, MsgStatus.PUSHED, MsgStatus.PROCESSING,
                      "pending", "pushed", "processing", "resending"):
                pending += 1
        out[name] = {"total": len(inbox.messages), "pending": pending, "states": dict(states)}
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(MAIL, "store"))
    ap.add_argument("--agent", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-prune", action="store_true")
    ap.add_argument("--skip-remind", action="store_true")
    ap.add_argument("--archive", action="store_true")
    args = ap.parse_args()

    config = load_config(os.path.join(args.data_dir, "config.json"))
    agents = config.get("agents", {})

    print("=== inbox stats (before) ===")
    before = inbox_stats(args.data_dir, agents)
    for name, st in sorted(before.items(), key=lambda x: -x[1]["pending"]):
        if st["pending"] or st["total"] > 100:
            print(f"  {name}: total={st['total']} pending={st['pending']} {st['states']}")

    if not args.skip_remind:
        from lib.reminder_cleanup import close_stale_reminders
        closed = close_stale_reminders(args.data_dir, agents)
        if closed:
            print("=== stale reminds closed ===")
            for k, v in closed.items():
                print(f"  {k}: {v}")

    if not args.skip_prune:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "inbox_prune", os.path.join(MAIL, "tools", "inbox-prune-notices.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        targets = [args.agent] if args.agent else list(agents.keys())
        total = 0
        for name in targets:
            n = mod.prune_agent(args.data_dir, name, dry_run=args.dry_run)
            if n:
                print(f"  pruned {name}: {n}")
            total += n
        print(f"total pruned: {total}" + (" (dry-run)" if args.dry_run else ""))

    if not args.dry_run:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "inbox_dedupe", os.path.join(MAIL, "tools", "inbox-dedupe.py")
        )
        dedupe_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dedupe_mod)
        deduped = 0
        targets = [args.agent] if args.agent else list(agents.keys())
        for name in targets:
            n = dedupe_mod.dedupe_agent(args.data_dir, name)
            if n:
                print(f"  deduped {name}: {n}")
            deduped += n
        if deduped:
            print(f"total deduped: {deduped}")

    if args.archive and not args.dry_run:
        from lib.archiver import archive_all
        archived = archive_all(
            args.data_dir, agents,
            archive_days=config.get("archive_days", 7),
            max_messages=config.get("archive_max_messages", 300),
        )
        if archived:
            print("=== archived ===")
            for k, v in archived.items():
                print(f"  {k}: {v}")

    if not args.dry_run:
        print("=== inbox stats (after) ===")
        after = inbox_stats(args.data_dir, agents)
        for name, st in sorted(after.items(), key=lambda x: -x[1]["pending"]):
            if st["pending"] or st["total"] > 100:
                print(f"  {name}: total={st['total']} pending={st['pending']} {st['states']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
