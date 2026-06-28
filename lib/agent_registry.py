"""Agent registry — scan mail/access/**/agent.json (schema mailbus-agent-v3)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from .constants import MAILBUS_ROOT

SCHEMA_V3 = "mailbus-agent-v3"
ACCESS_GLOB = "**/agent.json"


def mailbus_root(mail_root: Path | str | None = None) -> Path:
    if mail_root is not None:
        return Path(mail_root)
    return MAILBUS_ROOT


def access_dir(mail_root: Path | str | None = None) -> Path:
    return mailbus_root(mail_root) / "access"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def iter_agent_json_paths(mail_root: Path | str | None = None) -> Iterator[Path]:
    root = access_dir(mail_root)
    if not root.is_dir():
        return iter(())
    return root.glob(ACCESS_GLOB)


def load_agent_record(path: Path, *, mail_root: Path | None = None) -> dict[str, Any] | None:
    data = _read_json(path)
    agent_id = (data.get("agent_id") or "").strip()
    if not agent_id:
        return None
    framework = (data.get("framework") or "").strip()
    archetype = (data.get("archetype") or "").strip()
    record = dict(data)
    record.setdefault("schema", SCHEMA_V3)
    record["agent_id"] = agent_id
    record["framework"] = framework
    record["archetype"] = archetype
    record["_path"] = str(path)
    if mail_root is not None:
        try:
            record["_rel_path"] = path.relative_to(access_dir(mail_root)).as_posix()
        except ValueError:
            record["_rel_path"] = path.name
    return record


_AGENT_CACHE: dict[str, dict[str, dict[str, Any]]] = {}


def clear_agent_registry_cache() -> None:
    _AGENT_CACHE.clear()
    _scan_agent_json_files.cache_clear()


@lru_cache(maxsize=4)
def _scan_agent_json_files(mail_root_s: str) -> tuple[str, ...]:
    root = Path(mail_root_s)
    paths = sorted(p.resolve() for p in iter_agent_json_paths(root))
    return tuple(str(p) for p in paths)


def load_all_agents(*, mail_root: Path | str | None = None, refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Return {agent_id: agent_record} from access/**/agent.json."""
    root = mailbus_root(mail_root)
    key = str(root.resolve())
    if refresh:
        _AGENT_CACHE.pop(key, None)
        _scan_agent_json_files.cache_clear()
    cached = _AGENT_CACHE.get(key)
    if cached is not None:
        return cached

    agents: dict[str, dict[str, Any]] = {}
    for path_s in _scan_agent_json_files(key):
        record = load_agent_record(Path(path_s), mail_root=root)
        if not record:
            continue
        aid = record["agent_id"]
        if aid in agents:
            raise ValueError(f"duplicate agent_id in access/: {aid} ({path_s})")
        agents[aid] = record
    _AGENT_CACHE[key] = agents
    return agents


def get_agent(agent_id: str, *, mail_root: Path | str | None = None) -> dict[str, Any] | None:
    return load_all_agents(mail_root=mail_root).get(agent_id)


def list_agent_ids(*, mail_root: Path | str | None = None) -> list[str]:
    return sorted(load_all_agents(mail_root=mail_root))


def list_agents_by_framework(framework: str, *, mail_root: Path | str | None = None) -> list[str]:
    fw = (framework or "").strip()
    return sorted(
        aid for aid, rec in load_all_agents(mail_root=mail_root).items()
        if rec.get("framework") == fw
    )


def agent_archetypes(*, mail_root: Path | str | None = None) -> dict[str, str]:
    return {
        aid: rec["archetype"]
        for aid, rec in load_all_agents(mail_root=mail_root).items()
        if rec.get("archetype")
    }


def hermes_profile_agents(*, mail_root: Path | str | None = None) -> tuple[str, ...]:
    return tuple(list_agents_by_framework("hermes_profile", mail_root=mail_root))


def skill_paths_for_agent(agent_id: str, *, mail_root: Path | str | None = None) -> list[str]:
    rec = get_agent(agent_id, mail_root=mail_root)
    if not rec:
        return []
    skills = rec.get("skills") or []
    return [s for s in skills if isinstance(s, str) and s.strip()]


def _skill_id_from_rel(rel: str) -> str:
    rel = rel.replace("\\", "/").rstrip("/")
    name = Path(rel).name
    if name == "SKILL.md":
        return Path(rel).parent.name
    return name


def _skill_layer(rel: str) -> str:
    rel = rel.replace("\\", "/")
    if "/common/" in rel:
        return "L0"
    if "/frameworks/" in rel:
        return "L1"
    if "/roles/" in rel:
        return "L2"
    return "L?"


def _skill_type(rel: str) -> str:
    rel = rel.replace("\\", "/")
    if "/overlays/" in rel:
        return "role_overlay"
    if "/archetypes/" in rel:
        return "role_archetype"
    if "/frameworks/" in rel:
        return "framework_skill"
    if "/common/" in rel:
        if "mailbus-file-protocol" in rel:
            return "shared_skill"
        return "shared_skill"
    return "skill"


def skill_spec_from_path(rel: str, *, agent_id: str = "", framework: str = "") -> dict[str, Any]:
    rel = rel.replace("\\", "/").rstrip("/")
    sid = _skill_id_from_rel(rel)
    if sid == "mailbus-file-protocol":
        sid = "mailbus-file-protocol"
    elif sid == "agent-universal":
        sid = "agent-universal"
    elif rel.startswith("mail/skills/frameworks/"):
        fw = framework or Path(rel).name
        sid = f"framework-runtime-{fw.replace('_', '-')}"
    elif "/archetypes/" in rel:
        sid = f"role-{Path(rel).name}"
    elif "/overlays/" in rel and agent_id:
        sid = f"role-overlay-{agent_id}"

    skill_path = rel if rel.endswith("SKILL.md") else f"{rel}/SKILL.md"
    spec: dict[str, Any] = {
        "id": sid,
        "path": skill_path,
        "type": _skill_type(rel),
        "layer": _skill_layer(rel),
        "always": True,
    }
    if spec["type"] == "framework_skill":
        spec["framework"] = framework or Path(rel).name
    if spec["type"] == "role_archetype":
        spec["archetype"] = Path(rel).name
    if spec["type"] == "role_overlay":
        spec["agent_id"] = agent_id
    return spec


def layer_skills_for_agent(agent_id: str, framework: str | None = None, *, mail_root: Path | str | None = None) -> list[dict[str, Any]]:
    """Ordered L0–L2 skill specs for sync scripts (v3 access/ SoT)."""
    rec = get_agent(agent_id, mail_root=mail_root)
    if not rec:
        raise ValueError(f"unknown agent: {agent_id}")
    fw = framework or rec.get("framework") or ""
    specs: list[dict[str, Any]] = []
    for rel in skill_paths_for_agent(agent_id, mail_root=mail_root):
        specs.append(skill_spec_from_path(rel, agent_id=agent_id, framework=fw))
    return specs


def resolve_skill_src(rel: str, *, mail_root: Path | str | None = None) -> Path:
    """Resolve mail/skills/... or workspace-relative paths to absolute Path."""
    root = mailbus_root(mail_root)
    ai_tools = root.parent
    rel = (rel or "").replace("\\", "/")
    if rel.startswith("mail/adapters/") or rel.startswith("mail/roles/"):
        raise ValueError(f"legacy skill path removed (use mail/skills/): {rel}")
    if rel.startswith("mail/skills/"):
        tail = rel[len("mail/skills/"):]
        p = root / "skills" / tail
        if p.is_dir():
            return p / "SKILL.md"
        return p
    if rel.startswith(".codex/"):
        return ai_tools / rel
    if rel.startswith("store/"):
        return root / rel
    if rel.endswith("/SKILL.md"):
        return resolve_skill_src(rel[: -len("/SKILL.md")], mail_root=root)
    p = Path(rel)
    return p if p.is_absolute() else ai_tools / rel


def agent_config_type(agent_id: str, *, mail_root: Path | str | None = None) -> str:
    """Map agent.json framework → store/config.json agents[].type."""
    rec = get_agent(agent_id, mail_root=mail_root) or {}
    return (rec.get("framework") or "none").strip() or "none"


def hermes_sync_skills_dir(agent_id: str, *, mail_root: Path | str | None = None) -> Path:
    """Hermes L0–L2 skills sync target (v3: access/hermes/.sync/)."""
    root = mailbus_root(mail_root)
    return root / "access" / "hermes" / ".sync" / agent_id / "skills"
