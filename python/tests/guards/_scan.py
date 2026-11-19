"""守卫共用的 AST 扫描工具（不以 test_ 开头，避免被收集）。"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "python" / "mailbus"


class ModuleInfo:
    __slots__ = ("path", "tree", "parts", "is_package")

    def __init__(self, path: Path, tree: ast.Module, parts: list[str], is_package: bool) -> None:
        self.path = path
        self.tree = tree
        self.parts = parts
        self.is_package = is_package


def iter_modules(root: Path = PACKAGE_ROOT) -> Iterator[ModuleInfo]:
    """遍历包内所有 .py，返回模块信息（parts 为 mailbus 之后的分段）。"""
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root)
        is_package = rel.name == "__init__.py"
        parts = list(rel.parts[:-1]) if is_package else [*rel.parts[:-1], path.stem]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        yield ModuleInfo(path, tree, parts, is_package)


def absolute_imports(info: ModuleInfo) -> list[str]:
    """返回该模块所有 import 的绝对模块名（相对导入按包层级还原）。"""
    found: list[str] = []
    for node in ast.walk(info.tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    found.append(node.module)
            else:
                found.append(_resolve_relative(node, info))
    return [name for name in found if name]


def _resolve_relative(node: ast.ImportFrom, info: ModuleInfo) -> str:
    base = info.parts if info.is_package else info.parts[:-1]
    keep = len(base) - (node.level - 1)
    prefix = base[:keep] if keep > 0 else []
    tail = node.module.split(".") if node.module else []
    return ".".join(["mailbus", *prefix, *tail])
