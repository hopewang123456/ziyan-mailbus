#!/usr/bin/env python3
"""Ensure host Ollama via mailbus adapter (stock API/CLI only; no Ollama source changes).

Usage:
  python tools/ensure-ollama.py --data-dir store
  python tools/ensure-ollama.py --data-dir store --no-pull
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    import fcntl  # noqa: F401
except ImportError:
    from unittest.mock import MagicMock
    sys.modules["fcntl"] = MagicMock()

import contextlib
import lib.infra.utils as _utils


@contextlib.contextmanager
def _noop_file_lock(timeout=10.0, path=""):
    yield


_utils.file_lock = _noop_file_lock

from lib.infra.internal_llm.ollama_ensure import ensure_from_config


def main() -> int:
    ap = argparse.ArgumentParser(description="Ensure Ollama daemon + model")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    ap.add_argument("--no-start", action="store_true", help="do not start ollama serve if API down")
    ap.add_argument("--no-pull", action="store_true", help="do not pull missing model")
    ap.add_argument("--wait-seconds", type=float, default=60)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = ensure_from_config(
        os.path.abspath(args.data_dir),
        start=not args.no_start,
        pull=not args.no_pull,
        wait_seconds=args.wait_seconds,
    )
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif out.get("skipped"):
        print(f"[ensure-ollama] skip: {out.get('reason')}")
    elif out.get("ok"):
        print(f"[ensure-ollama] OK model={out.get('model')} @ {out.get('base_url')}")
    else:
        print(f"[ensure-ollama] FAIL: {out.get('error')}", file=sys.stderr)

    if out.get("skipped"):
        return 0
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
