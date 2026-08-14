"""解析 manifest、路径前缀与 host 路径规范化。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

MIGRATE_DIR = Path(__file__).resolve().parent
MAILBUS_CORE = MIGRATE_DIR.parent


def require_yaml() -> None:
    if yaml is None:
        raise SystemExit(
            "ERROR: PyYAML required for migrate. Install: pip install PyYAML  (or pip install -e mailbus-core)"
        )

def _old_prefixes() -> tuple[str, ...]:
    """迁移时识别的旧前缀；可用 MAILBUS_OLD_PREFIXES 覆盖（逗号分隔）。"""
    override = os.environ.get("MAILBUS_OLD_PREFIXES", "").strip()
    if override:
        return tuple(p.strip() for p in override.split(",") if p.strip())
    return (
        "/mnt/<OLD_MAILBUS_ROOT>",
        "<OLD_MAILBUS_ROOT>",
        "<OLD_MAILBUS_ROOT_BS>",
        "/mnt/<OLD_HERMES_DATA>",
        "<OLD_HERMES_DATA>",
        "<OLD_HERMES_DATA_BS>",
    )


# 兼容旧引用：默认取 _old_prefixes()
OLD_PREFIXES = _old_prefixes()


def load_manifest() -> dict[str, Any]:
    require_yaml()
    path = MIGRATE_DIR / "manifest.yaml"
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}


def install_prefix_from_env() -> Path:
    root = os.environ.get("MAILBUS_INSTALL_PREFIX", "").strip()
    if root:
        return Path(root).resolve()
    return MAILBUS_CORE.parent.resolve()


def resolve_path(env_name: str, install_prefix: Path | None = None) -> Path:
    """从 .env 或 manifest 默认推导目录。"""
    load_mailbus_env_keys()
    if os.environ.get(env_name):
        return Path(os.environ[env_name]).resolve()
    prefix = install_prefix or install_prefix_from_env()
    manifest = load_manifest()
    for section in ("required", "infra"):
        for item in manifest.get(section) or []:
            if item.get("env") == env_name:
                return (prefix / item["path"]).resolve()
    for item in manifest.get("framework_workspaces") or []:
        if item.get("env") == env_name:
            return (prefix / item.get("default_subpath", "")).resolve()
    return prefix / env_name.lower()


def load_mailbus_env_keys() -> None:
    env_file = MAILBUS_CORE / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip("'\"")
        if key and val and key not in os.environ:
            os.environ[key] = val


def to_wsl_path(path: Path) -> str:
    s = str(path.resolve()).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    if m:
        return f"/mnt/{m.group(1).lower()}/{m.group(2)}"
    return s


def collect_old_prefixes(install_prefix: Path) -> list[str]:
    """迁移时替换的旧前缀列表（含当前 install 的 WSL/Win 形式）。"""
    prefixes = list(OLD_PREFIXES)
    win = str(install_prefix).replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", win):
        prefixes.append(win)
        prefixes.append(to_wsl_path(install_prefix))
    else:
        prefixes.append(win)
    return prefixes


def manifest_entries(install_prefix: Path | None = None) -> list[dict[str, Any]]:
    prefix = install_prefix or install_prefix_from_env()
    manifest = load_manifest()
    entries: list[dict[str, Any]] = []
    for section in ("required", "infra"):
        for item in manifest.get(section) or []:
            env = item["env"]
            p = resolve_path(env, prefix) if os.environ.get(env) else prefix / item["path"]
            entries.append(
                {
                    "tier": section.rstrip("s") if section != "required" else "required",
                    "env": env,
                    "path": str(p),
                    "optional": item.get("optional", section != "required"),
                    "description": item.get("description", ""),
                    "exists": Path(p).exists(),
                }
            )
    return entries
