"""校验契约矩阵与 OpenAPI 的 path+method 集合完全一致。

用法：
    python tools/check_contract_matrix.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX = REPO_ROOT / "docs" / "plans" / "contract-matrix.md"
OPENAPI = REPO_ROOT / "shared" / "contracts" / "generated" / "openapi.json"

_METHOD = r"(?:GET|POST|PUT|PATCH|DELETE)"
_PAIR = re.compile(rf"\b({_METHOD}(?:/{_METHOD})*)\s+(/[A-Za-z0-9_{{}}./-]+)")


def matrix_pairs() -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        if "已废弃" in line:
            continue
        for methods, path in _PAIR.findall(line):
            clean = path.split("?")[0].rstrip("`")
            for method in methods.split("/"):
                pairs.add((method, clean))
    return pairs


def openapi_pairs() -> set[tuple[str, str]]:
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    pairs: set[tuple[str, str]] = set()
    for path, operations in spec["paths"].items():
        for method in operations:
            pairs.add((method.upper(), path))
    return pairs


def main() -> int:
    matrix = matrix_pairs()
    spec = openapi_pairs()
    only_matrix = sorted(matrix - spec)
    only_spec = sorted(spec - matrix)
    if only_matrix or only_spec:
        print(f"契约矩阵与 OpenAPI 不一致：matrix={len(matrix)} openapi={len(spec)}")
        for method, path in only_matrix:
            print(f"  矩阵有、OpenAPI 无：{method} {path}")
        for method, path in only_spec:
            print(f"  OpenAPI 有、矩阵无：{method} {path}")
        return 1
    print(f"契约一致：{len(spec)} 个 path+method")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
