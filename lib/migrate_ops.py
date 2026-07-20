"""Mailbus migrate CLI 逻辑 — 供 tools/mailbus.py 调用。"""

from __future__ import annotations

import sys
from pathlib import Path

MIGRATE_DIR = Path(__file__).resolve().parent.parent / "migrate"
if str(MIGRATE_DIR) not in sys.path:
    sys.path.insert(0, str(MIGRATE_DIR))

from bundle_export import export_bundle  # noqa: E402
from bundle_import import import_bundle  # noqa: E402
from paths import manifest_entries, install_prefix_from_env, MAILBUS_CORE  # noqa: E402
from write_env import write_env  # noqa: E402


def cmd_migrate_plan(_args) -> int:
    prefix = install_prefix_from_env()
    from lib.layout_guard import layout_report

    layout = layout_report(prefix)
    print(f"[migrate plan] install_prefix={prefix}")
    print(f"[migrate plan] MAILBUS_CORE={MAILBUS_CORE}")
    if layout.dedup_unsafe:
        print(f"  [FAIL] layout: {layout.message}")
        print("         勿对 mail/ 执行代码去重；先解除 junction 或物理拆分目录。")
    elif layout.core_is_reparse:
        print(f"  [WARN] layout: {layout.message}")
    else:
        print("  [OK] layout: mail/ 与 mailbus-core/ 独立")
    for entry in manifest_entries(prefix):
        flag = "OK" if entry["exists"] else ("WARN" if entry["optional"] else "MISSING")
        print(f"  [{flag}] {entry['env']}: {entry['path']}")
        if entry.get("description"):
            print(f"         {entry['description']}")
    return 0


def cmd_migrate_export(args) -> int:
    prefix = Path(args.prefix or install_prefix_from_env())
    out = Path(args.output or "mailbus-bundle.tar.gz")
    info = export_bundle(out, prefix, include_infra=not args.no_infra)
    print(f"[migrate export] wrote {info['output']}")
    if info.get("skipped"):
        print(f"[migrate export] skipped optional: {len(info['skipped'])}")
    return 0


def cmd_migrate_import(args) -> int:
    return import_bundle(
        Path(args.bundle),
        Path(args.prefix),
        dry_run=args.dry_run,
        skip_post=args.skip_post,
    )
