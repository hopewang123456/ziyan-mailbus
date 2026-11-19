"""G1 层依赖守卫：只允许单向依赖，禁止跨层穿越与反向依赖。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan import absolute_imports, iter_modules  # noqa: E402

_ALLOWED: dict[str, set[str]] = {
    "core": {"mailbus", "core"},
    "application": {"mailbus", "core", "application"},
    "adapters": {"mailbus", "core", "adapters"},
    "api": {"mailbus", "application", "core", "api"},
    "bootstrap": {"mailbus", "core", "application", "adapters", "api", "bootstrap"},
}


def _target_layer(module: str) -> str | None:
    parts = module.split(".")
    if not parts or parts[0] != "mailbus":
        return None
    return parts[1] if len(parts) > 1 else "mailbus"


def _violations() -> list[str]:
    problems: list[str] = []
    for info in iter_modules():
        if not info.parts:
            continue
        layer = info.parts[0]
        allowed = _ALLOWED.get(layer)
        if allowed is None:
            continue
        for module in absolute_imports(info):
            target = _target_layer(module)
            if target is None:
                continue
            if target not in allowed:
                problems.append(f"{info.path.name}: {layer} 不允许 import {module}")
            elif layer == "api" and target == "core" and not module.startswith("mailbus.core.shared"):
                problems.append(f"{info.path.name}: api 只允许使用 core.shared，实际 import {module}")
    return problems


def test_layers_only_depend_downwards() -> None:
    problems = _violations()
    assert not problems, "层依赖违规：\n" + "\n".join(problems)
