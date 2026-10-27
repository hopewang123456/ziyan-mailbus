"""双栈 API 面对拍（D13 四件套常设项 / PY4-A DoD）。

用法：
    # 双 serve 在跑（python 9814 / java 9815）
    python tools/api_surface_diff.py [--py http://127.0.0.1:9814] [--java http://127.0.0.1:9815]

    # 不起 python serve：直接用路由表生成（--py offline）
    python tools/api_surface_diff.py --py offline [--java http://127.0.0.1:9815]

输出：stdout 摘要 + JSON 报告（默认 docs/reports/api-surface-diff.json）。
判读：
    - python-only / java-only：单侧独有的端点（对等缺口或显式 501 域）
    - 双侧齐：path+method 集合一致（形状 schema 深比对随路由表化渐进）
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPORT_PATH = REPO / "docs" / "reports" / "api-surface-diff.json"


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def python_surface(base: str) -> dict:
    if base == "offline":
        sys.path.insert(0, str(REPO / "python"))
        from lib.api.openapi import build_openapi
        return build_openapi()
    return _fetch(f"{base}/api/openapi.json")


def java_surface(base: str) -> dict:
    return _fetch(f"{base}/v3/api-docs")


def surface_set(doc: dict) -> dict:
    """{（method, 归一化path）: summary}——OpenAPI 3.x 兼容抽取。

    路径参数段归一化为 ``{}``（python {id} 与 java {agent} 语义同路径）。
    """
    out: dict = {}
    for path, methods in (doc.get("paths") or {}).items():
        norm = "/".join("{}" if s.startswith("{") and s.endswith("}") else s
                        for s in path.split("/"))
        for method, entry in methods.items():
            if method in ("get", "post", "put", "patch", "delete"):
                out[(method.upper(), norm)] = (entry or {}).get("summary") or (entry or {}).get("description") or ""
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="mailbus 双栈 API 面对拍")
    ap.add_argument("--py", default="http://127.0.0.1:9814",
                    help="python serve base URL，或 offline=直接路由表生成")
    ap.add_argument("--java", default="http://127.0.0.1:9815")
    ap.add_argument("--out", default=str(REPORT_PATH))
    args = ap.parse_args()

    py_doc = python_surface(args.py)
    java_doc = java_surface(args.java)
    py_set = surface_set(py_doc)
    java_set = surface_set(java_doc)

    both = sorted(set(py_set) & set(java_set))
    py_only = sorted(set(py_set) - set(java_set))
    java_only = sorted(set(java_set) - set(py_set))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"python": args.py, "java": args.java},
        "summary": {
            "python_endpoints": len(py_set),
            "java_endpoints": len(java_set),
            "both": len(both),
            "python_only": len(py_only),
            "java_only": len(java_only),
        },
        "both": [{"method": m, "path": p, "py_summary": py_set[(m, p)], "java_summary": java_set[(m, p)]}
                 for m, p in both],
        "python_only": [{"method": m, "path": p, "summary": py_set[(m, p)]} for m, p in py_only],
        "java_only": [{"method": m, "path": p, "summary": java_set[(m, p)]} for m, p in java_only],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    s = report["summary"]
    print(f"双栈 API 面对拍：python {s['python_endpoints']} | java {s['java_endpoints']} | "
          f"双侧齐 {s['both']} | python-only {s['python_only']} | java-only {s['java_only']}")
    if py_only:
        print("\n[python-only]")
        for e in report["python_only"]:
            print(f"  {e['method']:6} {e['path']}  # {e['summary']}")
    if java_only:
        print("\n[java-only]")
        for e in report["java_only"]:
            print(f"  {e['method']:6} {e['path']}  # {e['summary']}")
    print(f"\n报告：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
