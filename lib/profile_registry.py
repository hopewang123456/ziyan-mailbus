"""Team-pack profile registry — skills, rules, archetype (separate from transport)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from .constants import TEAM_PACK_ROOT

SCHEMA_V1 = "team-profile-v1"
PROFILE_GLOB = "profiles/*/profile.json"


def team_pack_root(pack_root: Path | str | None = None) -> Path:
    if pack_root is not None:
        return Path(pack_root)
    return TEAM_PACK_ROOT


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def iter_profile_paths(pack_root: Path | str | None = None) -> Iterator[Path]:
    root = team_pack_root(pack_root)
    if not root.is_dir():
        return iter(())
    return root.glob(PROFILE_GLOB)


_PROFILE_CACHE: dict[str, dict[str, dict[str, Any]]] = {}


def clear_profile_registry_cache() -> None:
    _PROFILE_CACHE.clear()
    _scan_profile_files.cache_clear()


@lru_cache(maxsize=4)
def _scan_profile_files(pack_root_s: str) -> tuple[str, ...]:
    root = Path(pack_root_s)
    paths = sorted(p.resolve() for p in iter_profile_paths(root))
    return tuple(str(p) for p in paths)


def load_profile_record(path: Path) -> dict[str, Any] | None:
    data = _read_json(path)
    agent_id = (data.get("agent_id") or "").strip()
    if not agent_id:
        return None
    record = dict(data)
    record.setdefault("schema", SCHEMA_V1)
    record["agent_id"] = agent_id
    record["_path"] = str(path)
    return record


def load_all_profiles(*, pack_root: Path | str | None = None, refresh: bool = False) -> dict[str, dict[str, Any]]:
    root = team_pack_root(pack_root)
    key = str(root.resolve())
    if refresh:
        _PROFILE_CACHE.pop(key, None)
        _scan_profile_files.cache_clear()
    cached = _PROFILE_CACHE.get(key)
    if cached is not None:
        return cached

    profiles: dict[str, dict[str, Any]] = {}
    for path_s in _scan_profile_files(key):
        record = load_profile_record(Path(path_s))
        if not record:
            continue
        aid = record["agent_id"]
        if aid in profiles:
            raise ValueError(f"duplicate profile agent_id: {aid}")
        profiles[aid] = record
    _PROFILE_CACHE[key] = profiles
    return profiles


def get_profile(agent_id: str, *, pack_root: Path | str | None = None) -> dict[str, Any] | None:
    return load_all_profiles(pack_root=pack_root).get(agent_id)


def skill_paths_for_profile(agent_id: str, *, pack_root: Path | str | None = None) -> list[str]:
    rec = get_profile(agent_id, pack_root=pack_root)
    if not rec:
        return []
    return [s for s in rec.get("skills") or [] if isinstance(s, str) and s.strip()]


def rule_paths_for_profile(agent_id: str, *, pack_root: Path | str | None = None) -> list[str]:
    rec = get_profile(agent_id, pack_root=pack_root)
    if not rec:
        return []
    return [r for r in rec.get("rules") or [] if isinstance(r, str) and r.strip()]


def agent_archetypes(*, pack_root: Path | str | None = None) -> dict[str, str]:
    return {
        aid: rec["archetype"]
        for aid, rec in load_all_profiles(pack_root=pack_root).items()
        if rec.get("archetype")
    }
