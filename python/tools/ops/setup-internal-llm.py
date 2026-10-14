#!/usr/bin/env python3
"""Internal LLM 健康探测 + 可选 RAG 空索引重建（start-team bootstrap / smoke）。"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from lib.adapters.internal_llm.probe import probe_all  # noqa: E402
from lib.infra.internal_llm.startup import maybe_rebuild_rag_on_start  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe internal LLM providers and optional RAG bootstrap")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    ap.add_argument("--json", action="store_true", help="Print JSON report")
    ap.add_argument(
        "--rebuild-rag-if-empty",
        action="store_true",
        help="Rebuild RAG index when rebuild_on_start and chunk count is 0",
    )
    args = ap.parse_args()

    rebuild = maybe_rebuild_rag_on_start(args.data_dir) if args.rebuild_rag_if_empty else None
    report = probe_all(args.data_dir)
    if rebuild is not None:
        report["rag_bootstrap"] = rebuild

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "ready" if report.get("ready") else "not ready"
        print(f"internal-llm: {status} active={report.get('active_provider')}")
        if rebuild is not None:
            print(f"rag_bootstrap: {rebuild}")

    if not report.get("enabled"):
        return 0
    return 0 if report.get("ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
