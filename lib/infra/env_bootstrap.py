"""启动时加载 mailbus 环境变量（.env）。

加载链：`migrate/env.template` 或 `config/env.template` → 复制为项目根 `.env`
→ 本模块读 `.env` + `docker-agents/.env`。

框架工作区路径（Hermes/OpenClaw/Codex/DSH 等）**不再**默认猜
`MAILBUS_ROOT.parent/Agent/docker/...`；未在 .env / 设置页配置则为空，由 doctor 提示。
"""

from __future__ import annotations

import os
from pathlib import Path

_LOADED = False


def default_hermes_data_dir(repo_parent: Path) -> str:
    """兼容旧调用：仅当显式需要默认值时返回空串（不再猜 Agent/docker）。"""
    return ""


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
    root = Path(__file__).resolve().parents[2]
    _parse_env_file(root / ".env")
    _parse_env_file(root / "docker-agents" / ".env")
    if not os.environ.get("MAILBUS_INTERNAL_LLM_API_KEY"):
        fallback = (
            os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()
        if fallback:
            os.environ["MAILBUS_INTERNAL_LLM_API_KEY"] = fallback

    # WSL compose 必须用 docker-agents（与现有容器/网络一致）
    if os.name != "nt":
        os.environ["COMPOSE_PROJECT_NAME"] = "docker-agents"
    else:
        os.environ.setdefault("COMPOSE_PROJECT_NAME", "docker-agents")
    root_str = str(root)
    os.environ.setdefault("MAIL_DIR", root_str)
    os.environ.setdefault("MAILBUS_ROOT", os.environ.get("MAILBUS_ROOT") or root_str)
    data = (
        os.environ.get("MAILBUS_DATA")
        or os.environ.get("MAILBUS_DATA_DIR")
        or str(root / "store")
    )
    os.environ.setdefault("MAILBUS_DATA", data)
    os.environ.setdefault("MAILBUS_API_PORT", os.environ.get("MAILBUS_API_PORT") or "9814")
    os.environ.setdefault(
        "TEAM_PACK_ROOT",
        os.environ.get("TEAM_PACK_ROOT") or str(root / "team-pack"),
    )
    # 知识库根 / 框架工作区：仅尊重已有 env 或设置页写入；不 setdefault 到兄弟仓。


def mailbus_paths() -> dict[str, str]:
    """返回常用路径（需先 load_mailbus_env）。未配置的框架路径为空串。"""
    load_mailbus_env()
    root = Path(os.environ["MAILBUS_ROOT"]).resolve()
    compose = root / "docker-agents"
    return {
        "root": str(root),
        "mail_dir": os.environ.get("MAIL_DIR", str(root)),
        "data_dir": os.environ["MAILBUS_DATA"],
        "compose_dir": str(compose),
        "scripts_dir": str(root / "scripts"),
        "team_pack_root": os.environ.get("TEAM_PACK_ROOT", str(root / "team-pack")),
        "openclaw_workspace": os.environ.get("OPENCLAW_WORKSPACE", ""),
        "opencode_root": os.environ.get("OPENCODE_ROOT", ""),
        "node_modules": os.environ.get("NODE_MODULES", ""),
        "hermes_data": os.environ.get("HERMES_DATA", ""),
        "codex_workspace": os.environ.get("CODEX_WORKSPACE", ""),
        "codex_home": os.environ.get("CODEX_HOME", ""),
        "dsh_workspace": os.environ.get("DSH_WORKSPACE", ""),
        "skills_root": os.environ.get("MAILBUS_SKILLS_ROOT", str(root / "skills")),
        "rules_root": os.environ.get("MAILBUS_RULES_ROOT", str(root / "rules")),
        "plans_root": os.environ.get("MAILBUS_PLANS_ROOT", str(root / "plans")),
        "docs_root": os.environ.get("MAILBUS_DOCS_ROOT", str(root / "docs")),
        "identities_root": os.environ.get("MAILBUS_IDENTITIES_ROOT", str(root / "identities")),
        "api_port": os.environ["MAILBUS_API_PORT"],
        "compose_project": os.environ["COMPOSE_PROJECT_NAME"],
        "fix_portproxy_ps1": str(
            (root / "windows" / "fix-wsl-localhost.ps1")
            if (root / "windows" / "fix-wsl-localhost.ps1").is_file()
            else ""
        ),
        "windows_dir": str(root / "windows"),
        "ensure_ollama_ps1": str(root / "tools" / "ensure-ollama.py"),
        "run_dir": str(root / "run"),
        "compose_override": str(compose / "docker-compose.override.yml"),
    }
