#!/usr/bin/env python3
"""同步 Google A2A 协议版本到 store/config/a2a-protocol.json。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.constants import MAILBUS_ROOT
from lib.utils import json_read, json_write


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync A2A protocol tracker")
    ap.add_argument("--data-dir", type=Path, default=MAILBUS_ROOT / "store")
    ap.add_argument("--latest-release", default="1.0.1")
    ap.add_argument("--negotiated", default="1.0")
    args = ap.parse_args()

    data_dir = args.data_dir
    cfg_dir = data_dir / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    target = cfg_dir / "a2a-protocol.json"
    tpl = MAILBUS_ROOT / "config" / "a2a-protocol.template.json"
    doc = json_read(str(tpl), {}) if tpl.is_file() else {}
    if target.is_file():
        doc.update(json_read(str(target), {}))

    prev_release = doc.get("wire_version_latest_release")
    doc["wire_version_negotiated"] = args.negotiated
    doc["wire_version_latest_known"] = args.latest_release
    doc["wire_version_latest_release"] = args.latest_release
    doc["last_sync_at"] = datetime.now(timezone.utc).isoformat()
    doc["last_sync_source"] = "a2a-sync-spec.py"
    json_write(str(target), doc)

    if prev_release and prev_release != args.latest_release:
        minor_changed = prev_release.rsplit(".", 1)[0] != args.latest_release.rsplit(".", 1)[0]
        if minor_changed:
            print(f"WARN: minor release change {prev_release} -> {args.latest_release}")
        else:
            print(f"patch release {prev_release} -> {args.latest_release}")
    print(f"updated {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
