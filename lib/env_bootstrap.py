"""启动时加载 mailbus 环境变量（.env）。

加载链（#36）：`config/env.template` → 复制为 `mail/.env` → 本模块读
`mail/.env` + `docker-agents/.env`；Shell 脚本用 `docker-agents/lib/mailbus-env.sh`。
"""

from __future__ import annotations

import os
from pathlib import Path

_LOADED = False


def _parse_env_file(path: Path) -> None:
    if not path.is_file():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'\"")
            if not key or not val:
                continue
            if key not in os.environ or not os.environ.get(key):
                os.environ[key] = val


def load_mailbus_env() -> None:
    """加载项目根 .env 与 docker-agents/.env（后者不覆盖已有变量）。"""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    root = Path(__file__).resolve().parent.parent
    _parse_env_file(root / ".env")
    _parse_env_file(root / "docker-agents" / ".env")
    # DeepSeek 别名 → mailbus remote LLM
    if not os.environ.get("MAILBUS_INTERNAL_LLM_API_KEY"):
        fallback = (
            os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()
        if fallback:
            os.environ["MAILBUS_INTERNAL_LLM_API_KEY"] = fallback
