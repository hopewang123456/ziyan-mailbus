"""Agent transport registry — scan access/transport/**/transport.json."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from .constants import (
    MAILBUS_ROOT,
    MAILBUS_SKILLS_ROOT,
    TEAM_PACK_SKILLS_ROOT,
)
from . import profile_registry as profiles

SCHEMA_TRANSPORT = "mailbus-transport-v1"
TRANSPORT_GLOB = "transport/*/transport.json"


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


def iter_transport_paths(mail_root: Path | str | None = None) -> Iterator[Path]:
    root = access_dir(mail_root) / "transport"
    if not root.is_dir():
        return iter(())
    return root.glob("*/transport.json")


def load_transport_record(path: Path, *, mail_root: Path | None = None) -> dict[str, Any] | None:
    data = _read_json(path)
    agent_id = (data.get("agent_id") or path.parent.name or "").strip()
    if not agent_id:
        return None
    framework = (data.get("framework") or "").strip()
    record = dict(data)
    record.setdefault("schema", SCHEMA_TRANSPORT)
    record["agent_id"] = agent_id
    record["framework"] = framework
    record["_path"] = str(path)
    if mail_root is not None:
        try:
            record["_rel_path"] = path.relative_to(access_dir(mail_root)).as_posix()
        except ValueError:
            record["_rel_path"] = path.name
    prof = profiles.get_profile(agent_id)
    if prof:
        record["archetype"] = prof.get("archetype") or ""
        record["skills"] = list(prof.get("skills") or [])
        record["rules"] = list(prof.get("rules") or [])
        record["display_name"] = prof.get("display_name") or agent_id
        record["identity_ref"] = prof.get("identity_ref") or ""
    return record


_AGENT_CACHE: dict[str, dict[str, dict[str, Any]]] = {}


def clear_agent_registry_cache() -> None:
    _AGENT_CACHE.clear()
    _scan_transport_files.cache_clear()
    profiles.clear_profile_registry_cache()


@lru_cache(maxsize=4)
def _scan_transport_files(mail_root_s: str) -> tuple[str, ...]:
    root = Path(mail_root_s)
    paths = sorted(p.resolve() for p in iter_transport_paths(root))
    return tuple(str(p) for p in paths)


def load_all_agents(*, mail_root: Path | str | None = None, refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Return {agent_id: transport+profile merged record}."""
    root = mailbus_root(mail_root)
    key = str(root.resolve())
    if refresh:
        _AGENT_CACHE.pop(key, None)
        _scan_transport_files.cache_clear()
        profiles.clear_profile_registry_cache()
    cached = _AGENT_CACHE.get(key)
    if cached is not None:
        return cached

    agents: dict[str, dict[str, Any]] = {}
    for path_s in _scan_transport_files(key):
        record = load_transport_record(Path(path_s), mail_root=root)
        if not record:
            continue
        aid = record["agent_id"]
        if aid in agents:
            raise ValueError(f"duplicate agent_id in transport/: {aid} ({path_s})")
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
    return profiles.agent_archetypes()


def hermes_profile_agents(*, mail_root: Path | str | None = None) -> tuple[str, ...]:
    return tuple(list_agents_by_framework("hermes_profile", mail_root=mail_root))


def skill_paths_for_agent(agent_id: str, *, mail_root: Path | str | None = None) -> list[str]:
    return profiles.skill_paths_for_profile(agent_id)


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
        return "shared_skill"
    return "skill"


def skill_spec_from_path(rel: str, *, agent_id: str = "", framework: str = "") -> dict[str, Any]:
    rel = rel.replace("\\", "/").rstrip("/")
    sid = _skill_id_from_rel(rel)
    if sid == "mailbus-file-protocol":
        sid = "mailbus-file-protocol"
    elif sid == "agent-universal":
        sid = "agent-universal"
    elif "/frameworks/" in rel:
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
    """Ordered L0–L2 skill specs from team-pack profile."""
    rec = get_agent(agent_id, mail_root=mail_root)
    if not rec:
        raise ValueError(f"unknown agent: {agent_id}")
    fw = framework or rec.get("framework") or ""
    specs: list[dict[str, Any]] = []
    for rel in skill_paths_for_agent(agent_id, mail_root=mail_root):
        specs.append(skill_spec_from_path(rel, agent_id=agent_id, framework=fw))
    return specs


def resolve_skill_src(rel: str, *, mail_root: Path | str | None = None) -> Path:
    """Resolve mail/skills/ or legacy mailbus-core/skills/ paths to absolute Path.

    物理根由 MAILBUS_SKILLS_ROOT / TEAM_PACK_SKILLS_ROOT 决定（见 lib.constants）。
    """
    root = mailbus_root(mail_root)
    skills = MAILBUS_SKILLS_ROOT
    pack_skills = TEAM_PACK_SKILLS_ROOT
    ai_tools = root.parent
    rel = (rel or "").replace("\\", "/")
    if rel.startswith("mailbus-core/skills/") or rel.startswith("mail/skills/"):
        prefix = "mailbus-core/skills/" if rel.startswith("mailbus-core/skills/") else "mail/skills/"
        tail = rel[len(prefix):]
        if tail.startswith("common/agent-universal") or tail.startswith("roles/"):
            p = pack_skills / tail
        else:
            p = skills / tail
        return (p / "SKILL.md") if p.is_dir() else p
    if rel.startswith("team-pack/skills/"):
        tail = rel[len("team-pack/skills/"):]
        p = pack_skills / tail
        return (p / "SKILL.md") if p.is_dir() else p
    if rel.startswith(".codex/"):
        return root / rel
    if rel.endswith("/SKILL.md"):
        return resolve_skill_src(rel[: -len("/SKILL.md")], mail_root=root)
    p = Path(rel)
    return p if p.is_absolute() else ai_tools / rel


def agent_config_type(agent_id: str, *, mail_root: Path | str | None = None) -> str:
    rec = get_agent(agent_id, mail_root=mail_root) or {}
    return (rec.get("framework") or "none").strip() or "none"


def hermes_sync_skills_dir(agent_id: str, *, mail_root: Path | str | None = None) -> Path:
    root = mailbus_root(mail_root)
    return root / "access" / "hermes" / ".sync" / agent_id / "skills"
