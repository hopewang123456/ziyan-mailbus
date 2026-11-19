"""G7 状态唯一守卫：状态枚举与语义标签只允许定义在 core。"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan import iter_modules  # noqa: E402

_STATE_CLASS = re.compile(r"^\w*(State|Status)$")
_TAG_CONST = re.compile(r"STATE_TAG")


def test_state_definitions_live_only_in_core() -> None:
    problems: list[str] = []
    for info in iter_modules():
        if info.parts and info.parts[0] == "core":
            continue
        for node in ast.walk(info.tree):
            if isinstance(node, ast.ClassDef) and _STATE_CLASS.match(node.name):
                problems.append(f"{info.path.name}: 类 {node.name} 定义在 core 之外")
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and _TAG_CONST.search(target.id):
                        problems.append(f"{info.path.name}: 常量 {target.id} 定义在 core 之外")
    assert not problems, "状态模型出现多个真相源：\n" + "\n".join(problems)
