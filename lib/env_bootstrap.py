"""启动时加载 mailbus 环境变量（.env）。

加载链：`migrate/env.template` 或 `config/env.template` → 复制为 `mailbus-core/.env`
→ 本模块读 `.env` + `docker-agents/.env`。
"""

from __future__ import annotations

import os
from pathlib import Path

_LOADED = False


def default_hermes_data_dir(repo_parent: Path) -> str:
    """Hermes 数据目录默认在 ai_tools 同级 E:/hermes-data/.hermes（非 ai_tools/hermes-data）。"""
    candidates = (
        repo_parent.parent / "hermes-data" / ".hermes",
        repo_parent / "hermes-data" / ".hermes",
    )
    for path in candidates:
        if path.is_dir():
            return str(path)
    return str(candidates[0])


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
    if not os.environ.get("MAILBUS_INTERNAL_LLM_API_KEY"):
        fallback = (
            os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()
        if fallback:
            os.environ["MAILBUS_INTERNAL_LLM_API_KEY"] = fallback

    # 与 docker-agents/lib/mailbus-env.sh 对齐；WSL compose 必须用 docker-agents（与现有容器/网络一致）
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

    parent = Path(os.environ["MAILBUS_ROOT"]).resolve().parent
    os.environ.setdefault(
        "OPENCLAW_WORKSPACE",
        os.environ.get("OPENCLAW_WORKSPACE") or str(parent / "openclaw_space"),
    )
    os.environ.setdefault(
        "OPENCODE_ROOT",
        os.environ.get("OPENCODE_ROOT") or str(parent / "opencode"),
    )
    os.environ.setdefault(
        "NODE_MODULES",
        os.environ.get("NODE_MODULES") or str(parent / "node_modules"),
    )
    if not os.environ.get("HERMES_DATA"):
        os.environ["HERMES_DATA"] = default_hermes_data_dir(parent)
    os.environ.setdefault(
        "TEAM_PACK_ROOT",
        os.environ.get("TEAM_PACK_ROOT") or str(parent / "team-pack"),
    )
    os.environ.setdefault(
        "LINGXIAO_WORKSPACE",
        os.environ.get("LINGXIAO_WORKSPACE") or str(parent / "lingxiao"),
    )
    # 知识库根：未设置时不 setdefault，由 constants 回落到仓库内 demo 路径。
    # 本机开发：靠 junction（mail/skills → Vault）+ docker-compose.override.yml；
    # 不要用 .env 把 MAILBUS_*_ROOT 指到 Vault（避免与 junction 双源）。
    # CI/publish：可用 MAILBUS_*_ROOT / TEAM_PACK_*_ROOT 覆盖到仓库相对路径。


def mailbus_paths() -> dict[str, str]:
    """返回常用路径（需先 load_mailbus_env）。"""
    load_mailbus_env()
    root = Path(os.environ["MAILBUS_ROOT"]).resolve()
    repo_parent = root.parent
    compose = root / "docker-agents"
    scripts = repo_parent / "scripts"
    hermes_data = os.environ.get("HERMES_DATA") or default_hermes_data_dir(repo_parent)
    return {
        "root": str(root),
        "mail_dir": os.environ.get("MAIL_DIR", str(root)),
        "data_dir": os.environ["MAILBUS_DATA"],
        "compose_dir": str(compose),
        "scripts_dir": str(scripts),
        "team_pack_root": os.environ.get("TEAM_PACK_ROOT", str(repo_parent / "team-pack")),
        "openclaw_workspace": os.environ.get("OPENCLAW_WORKSPACE", str(repo_parent / "openclaw_space")),
        "opencode_root": os.environ.get("OPENCODE_ROOT", str(repo_parent / "opencode")),
        "node_modules": os.environ.get("NODE_MODULES", str(repo_parent / "node_modules")),
        "hermes_data": hermes_data,
        "lingxiao_workspace": os.environ.get("LINGXIAO_WORKSPACE", str(repo_parent / "lingxiao")),
        "skills_root": os.environ.get("MAILBUS_SKILLS_ROOT", str(root / "skills")),
        "rules_root": os.environ.get("MAILBUS_RULES_ROOT", str(root / "rules")),
        "plans_root": os.environ.get("MAILBUS_PLANS_ROOT", str(root / "plans")),
        "docs_root": os.environ.get("MAILBUS_DOCS_ROOT", str(root / "docs")),
        "identities_root": os.environ.get("MAILBUS_IDENTITIES_ROOT", str(root / "identities")),
        "team_pack_skills_root": os.environ.get(
            "TEAM_PACK_SKILLS_ROOT",
            str(Path(os.environ.get("TEAM_PACK_ROOT", str(repo_parent / "team-pack"))) / "skills"),
        ),
        "team_pack_rules_root": os.environ.get(
            "TEAM_PACK_RULES_ROOT",
            str(Path(os.environ.get("TEAM_PACK_ROOT", str(repo_parent / "team-pack"))) / "rules"),
        ),
        "api_port": os.environ["MAILBUS_API_PORT"],
        "compose_project": os.environ["COMPOSE_PROJECT_NAME"],
        "fix_portproxy_ps1": str(scripts / "fix-wsl-localhost.ps1"),
        "ensure_ollama_ps1": str(compose / "ensure-ollama.ps1"),
        "run_dir": str(root / "run"),
        "compose_override": str(compose / "docker-compose.override.yml"),
    }
