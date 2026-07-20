#!/usr/bin/env python3
"""审计闭环：consume audit 文件 + 从审查官 chain 步骤补写 audit_log。"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.audit_dispatch import list_pending_audit_tasks, reconcile_pending_audits


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=os.environ.get("MAILBUS_DATA", "store"))
    args = p.parse_args()
    data_dir = os.path.abspath(args.data_dir)
    before = len(list_pending_audit_tasks(data_dir, 500))
    out = reconcile_pending_audits(data_dir)
    after = len(list_pending_audit_tasks(data_dir, 500))
    print(f"consumed={out.get('consumed', 0)} backfilled={out.get('backfilled', 0)}")
    print(f"pending_audit: {before} -> {after}")
    return 0 if after == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
