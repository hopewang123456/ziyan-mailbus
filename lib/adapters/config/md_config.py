"""Markdown / YAML-frontmatter agent config (Vault identities)."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

from lib.domain.types import AgentRef

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def resolve_identities_root(
    *,
    config: Mapping[str, Any] | None = None,
    override: str | None = None,
) -> str:
    """MAILBUS_IDENTITIES_ROOT -> config.identities_root -> default constant."""
    if override:
        return str(override)
    env = (os.environ.get("MAILBUS_IDENTITIES_ROOT") or "").strip()
    if env:
        return env
    if isinstance(config, Mapping):
        cfg = config.get("identities_root") or (config.get("paths") or {}).get("identities_root")
        if cfg:
            return str(cfg)
    try:
        from lib.infra.constants import MAILBUS_IDENTITIES_ROOT_STR, PROJECT_ROOT_STR

        default = MAILBUS_IDENTITIES_ROOT_STR
        if os.path.isdir(default):
            return default
        repo_config = os.path.join(PROJECT_ROOT_STR, "config")
        if os.path.isdir(repo_config):
            return repo_config
        return default
    except Exception:
        return os.path.join(".", "identities")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body). Empty dict when no YAML fence."""
    m = _FRONTMATTER_RE.match(text or "")
    if not m:
        return {}, text or ""
    raw = m.group(1)
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return {}, text or ""
    if not isinstance(data, dict):
        return {}, text[m.end() :]
    return data, text[m.end() :]


def _entry_from_frontmatter(agent_id: str, fm: Mapping[str, Any]) -> dict[str, Any]:
    aid = str(fm.get("id") or fm.get("agent_id") or agent_id).strip() or agent_id
    framework = str(fm.get("type") or fm.get("framework") or "").strip()
    role = str(fm.get("role_id") or fm.get("role") or "").strip()
    mount = str(fm.get("mount_mode") or fm.get("mount") or "").strip()
    enabled = fm.get("enabled", True)
    entry: dict[str, Any] = {
        "type": framework,
        "framework": framework,
        "role_id": role,
        "role": role,
        "mount_mode": mount,
        "mount": mount,
        "enabled": bool(enabled),
        "source": "md",
    }
    for k, v in fm.items():
        if k not in entry and k not in {"id", "agent_id"}:
            entry[k] = v
    entry["_agent_id"] = aid
    return entry


def _candidate_md_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    out: list[Path] = []
    agents_dir = root / "agents"
    if agents_dir.is_dir():
        out.extend(sorted(agents_dir.glob("*.md")))
    out.extend(sorted(root.glob("*.md")))
    # 各框架原生身份载体（计划 7b）：SOUL.md / IDENTITY.md / CLAUDE.md
    for pattern in ("*/SOUL.md", "*/IDENTITY.md", "*/CLAUDE.md"):
        out.extend(sorted(root.glob(pattern)))
    seen: set[str] = set()
    unique: list[Path] = []
    for p in out:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        if p.name.lower() in {"overview.md", "readme.md", "index.md"}:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def _agent_id_for_path(path: Path, root: Path) -> str:
    if path.name.upper() in {"SOUL.MD", "IDENTITY.MD", "CLAUDE.MD"}:
        return path.parent.name
    stem = path.stem
    if stem.lower().endswith("-soul"):
        return stem[: -len("-soul")]
    return stem


class MdAgentsConfig:
    """Read-only agents map sourced from Markdown YAML frontmatter."""

    def __init__(self, identities_root: str) -> None:
        self.identities_root = identities_root
        self._root = Path(identities_root)

    def list_agent_files(self) -> list[Path]:
        return _candidate_md_files(self._root)

    def load_agents_map(self) -> dict[str, dict[str, Any]]:
        agents: dict[str, dict[str, Any]] = {}
        for path in self.list_agent_files():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            fm, _body = parse_frontmatter(text)
            if not fm:
                continue
            default_id = _agent_id_for_path(path, self._root)
            entry = _entry_from_frontmatter(default_id, fm)
            aid = str(entry.pop("_agent_id"))
            entry["_md_path"] = str(path)
            agents[aid] = entry
        return agents

    def get_agent_entry(self, agent_id: str) -> dict[str, Any] | None:
        return self.load_agents_map().get(agent_id)

    def get_agent(self, agent_id: str) -> AgentRef | None:
        entry = self.get_agent_entry(agent_id)
        if not entry:
            return None
        return AgentRef(
            agent_id=agent_id,
            framework=str(entry.get("type") or entry.get("framework") or ""),
            role_id=str(entry.get("role_id") or entry.get("role") or ""),
            mount=str(entry.get("mount_mode") or entry.get("mount") or ""),
            enabled=bool(entry.get("enabled", True)),
        )

    def list_agents(self) -> list[AgentRef]:
        out: list[AgentRef] = []
        for aid, entry in self.load_agents_map().items():
            out.append(
                AgentRef(
                    agent_id=aid,
                    framework=str(entry.get("type") or entry.get("framework") or ""),
                    role_id=str(entry.get("role_id") or entry.get("role") or ""),
                    mount=str(entry.get("mount_mode") or entry.get("mount") or ""),
                    enabled=bool(entry.get("enabled", True)),
                )
            )
        return out

    def agent_mtime(self, agent_id: str) -> float | None:
        entry = self.get_agent_entry(agent_id)
        if not entry:
            return None
        path = entry.get("_md_path")
        if not path:
            return None
        try:
            return os.path.getmtime(str(path))
        except OSError:
            return None


def build_md_agents_config(
    *,
    data_dir: str = "",
    identities_root: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> MdAgentsConfig:
    root = resolve_identities_root(config=config, override=identities_root)
    return MdAgentsConfig(root)
