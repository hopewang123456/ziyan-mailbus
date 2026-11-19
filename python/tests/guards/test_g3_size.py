"""G3 体量守卫：单文件 ≤400 行、单函数 ≤50 行。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan import iter_modules  # noqa: E402

MAX_FILE_LINES = 400
MAX_FUNCTION_LINES = 50


def _violations() -> list[str]:
    problems: list[str] = []
    for info in iter_modules():
        lines = info.path.read_text(encoding="utf-8").count("\n") + 1
        if lines > MAX_FILE_LINES:
            problems.append(f"{info.path.name}: {lines} 行 > {MAX_FILE_LINES}")
        for node in ast.walk(info.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                size = (node.end_lineno or node.lineno) - node.lineno + 1
                if size > MAX_FUNCTION_LINES:
                    problems.append(f"{info.path.name}:{node.lineno} {node.name}() {size} 行")
    return problems


def test_file_and_function_size() -> None:
    problems = _violations()
    assert not problems, "体量超限：\n" + "\n".join(problems)
