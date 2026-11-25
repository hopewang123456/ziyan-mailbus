"""G4 路由薄守卫：路由函数只做协议转换。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan import PACKAGE_ROOT  # noqa: E402

ROUTERS_DIR = PACKAGE_ROOT / "api" / "routers"
MAX_ROUTER_LINES = 25


def test_router_functions_are_thin() -> None:
    problems: list[str] = []
    for path in sorted(ROUTERS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                size = (node.end_lineno or node.lineno) - node.lineno + 1
                if size > MAX_ROUTER_LINES:
                    problems.append(f"{path.name}:{node.lineno} {node.name}() {size} 行")
    assert not problems, "路由函数过长（业务逻辑应下沉到 application）：\n" + "\n".join(
        problems
    )
