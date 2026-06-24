#!/usr/bin/env python3
"""一次性：重建 catalog 索引并打印摘要。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.catalog_search import index_catalog, search_catalog, list_external_tools_summary
from lib.utils import json_read


def main() -> int:
    data_dir = os.path.join(ROOT, "store")
    agents = json_read(os.path.join(data_dir, "config.json"), {}).get("agents", {})
    n = index_catalog(data_dir, agents)
    print(f"catalog indexed: {n} entries")
    hits = search_catalog(data_dir, "dify", limit=5)
    print(f"search 'dify': {len(hits)} hits")
    for h in hits[:3]:
        print(f"  - [{h['kind']}] {h['title']}")
    summary = list_external_tools_summary(data_dir)
    print(f"external-tools: {len(summary.get('tools', []))} tools")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
