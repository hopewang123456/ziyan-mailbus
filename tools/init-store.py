#!/usr/bin/env python3
"""Thin CLI wrapper — `python tools/init-store.py --fresh`."""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lib.constants import DEFAULT_DATA_DIR  # noqa: E402
from lib.init_store import run_init_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="mailbus init-store — rebuild runtime store from SoT")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="Runtime store directory")
    parser.add_argument("--fresh", action="store_true", help="Wipe and rebuild store/")
    parser.add_argument("--merge", action="store_true", help="Merge SoT overrides into existing store/config.json")
    args = parser.parse_args()
    if args.merge:
        from lib.init_store import run_merge_store_config
        return run_merge_store_config(args.data_dir)
    return run_init_store(args.data_dir, fresh=args.fresh)


if __name__ == "__main__":
    raise SystemExit(main())
