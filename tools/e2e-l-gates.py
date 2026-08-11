#!/usr/bin/env python3
"""Thin CLI for Wave C L-gates — business lives in lib.application.ops.e2e_gates."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.application.ops.e2e_gates import (  # noqa: E402
    run_all_gates,
    run_l_desktop,
    run_l_inbox,
    run_l_notice,
    run_l_pipeline,
)

_GATES = {
    "inbox": run_l_inbox,
    "pipeline": run_l_pipeline,
    "notice": run_l_notice,
    "desktop": run_l_desktop,
    "all": run_all_gates,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Mailbus product L-gates E2E (fixture store)")
    p.add_argument(
        "--gate",
        choices=sorted(_GATES),
        default="all",
        help="Which gate to run (default: all)",
    )
    p.add_argument(
        "--data-dir",
        default="",
        help="Fixture data_dir (default: temp dir; never use production store/)",
    )
    p.add_argument("--json", action="store_true", help="Print full JSON result")
    args = p.parse_args(argv)

    if args.data_dir:
        data_dir = args.data_dir
        cleanup = None
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="mailbus-e2e-l-")
        data_dir = cleanup.name

    try:
        result = _GATES[args.gate](data_dir)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            ok = result.get("ok")
            print(f"gate={args.gate} ok={ok} data_dir={data_dir}")
            if args.gate == "all":
                for name, g in (result.get("gates") or {}).items():
                    print(f"  {name}: ok={g.get('ok')}")
        return 0 if result.get("ok") else 1
    finally:
        if cleanup is not None:
            cleanup.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
