#!/usr/bin/env python3
"""诊所平台探测 — 按当前启动平台校验 Agent 框架实例。

跨平台（win32 / wsl / linux / docker）通过 platform_probe 适配器统一探测，
输出结构化 JSON（stdout），供 Dashboard 诊所 / CLI 使用。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe Agent framework instances on the current platform")
    ap.add_argument("--json", action="store_true", help="emit JSON to stdout")
    ap.add_argument("--data-dir", default=os.environ.get("MAILBUS_DATA_DIR", os.environ.get("DATA_DIR", os.path.join(ROOT, "store"))))
    ap.add_argument("--framework", default="", help="probe a single framework/instance (default: all)")
    args = ap.parse_args()

    from lib.adapters.ops.platform_probe import get_platform_probe
    from lib.infra.utils import json_read

    config_path = os.path.join(os.path.abspath(args.data_dir), "config.json")
    config = json_read(config_path, {}) if os.path.isfile(config_path) else {}

    adapter = get_platform_probe()
    if args.framework:
        probes = [adapter.probe(args.framework, args.framework)]
    else:
        probes = adapter.probe_all(config)

    rows = [
        {
            "framework": p.framework,
            "instance": p.instance,
            "platform": p.platform,
            "ok": p.ok,
            "detail": p.detail,
        }
        for p in probes
    ]
    result = {
        "ok": all(p.ok for p in probes) if probes else False,
        "platform": adapter.platform_name,
        "count": len(probes),
        "instances": rows,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"platform={adapter.platform_name} instances={len(rows)}")
        for p in probes:
            flag = "OK" if p.ok else "FAIL"
            print(f"  {flag} {p.instance} ({p.framework}) — {p.detail or p.platform}")
    return 0 if result["ok"] or not probes else 1


if __name__ == "__main__":
    raise SystemExit(main())
