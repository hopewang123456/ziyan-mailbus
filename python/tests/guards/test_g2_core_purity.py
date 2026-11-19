"""G2 内核纯净守卫：core 不得出现第三方依赖与 IO。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan import absolute_imports, iter_modules  # noqa: E402

_ALLOWED_ROOTS = {
    "__future__",
    "abc",
    "collections",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "functools",
    "itertools",
    "math",
    "re",
    "typing",
    "uuid",
}

_BANNED_CALLS = {"open", "exec", "eval", "input"}


def _violations() -> list[str]:
    problems: list[str] = []
    for info in iter_modules():
        if not info.parts or info.parts[0] != "core":
            continue
        for module in absolute_imports(info):
            root = module.split(".")[0]
            if root != "mailbus" and root not in _ALLOWED_ROOTS:
                problems.append(f"{info.path.name}: core 不允许依赖 {module}")
        for node in ast.walk(info.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in _BANNED_CALLS:
                    problems.append(f"{info.path.name}: core 不允许调用 {node.func.id}()")
    return problems


def test_core_is_pure() -> None:
    problems = _violations()
    assert not problems, "内核纯净违规：\n" + "\n".join(problems)
