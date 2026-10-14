"""Team-pack profile registry — skills, rules, archetype (separate from transport).

主源已迁移到 Obsidian 人物索引（`02-members/022-category/*/022N3-persons/*/022N32-skills.md`
frontmatter `skills[]`/`rules[]`）。`profile.json` 仅保留非技能字段
（`archetype/display_name/identity_ref`），作为 fallback。

人物索引不可用时（CI / 未配置 Vault）自动回退 team-pack profile.json。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from lib.infra.constants import AGENT_VAULT_ROOT, TEAM_PACK_ROOT
from .md_config import parse_frontmatter

SCHEMA_V1 = "team-profile-v1"
PROFILE_GLOB = "profiles/*/profile.json"
PERSON_INDEX_GLOB = "02-members/022-category/*/*-persons/*/*2-skills.md"


def team_pack_root(pack_root: Path | str | None = None) -> Path:
    if pack_root is not None:
        return Path(pack_root)
    return TEAM_PACK_ROOT


def vault_agent_root(vault_root: Path | str | None = None) -> Path:
    if vault_root is not None:
        return Path(vault_root)
    return AGENT_VAULT_ROOT


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


def iter_person_index_paths(vault_root: Path | str | None = None) -> Iterator[Path]:
    root = vault_agent_root(vault_root)
    if not root.is_dir():
        return iter(())
    return root.glob(PERSON_INDEX_GLOB)


_PROFILE_CACHE: dict[str, dict[str, dict[str, Any]]] = {}


def clear_profile_registry_cache() -> None:
    _PROFILE_CACHE.clear()
    _scan_profile_files.cache_clear()
    _scan_person_index_files.cache_clear()
    _load_vault_frontmatter.cache_clear()


@lru_cache(maxsize=4)
def _scan_profile_files(pack_root_s: str) -> tuple[str, ...]:
    root = Path(pack_root_s)
    paths = sorted(p.resolve() for p in iter_profile_paths(root))
    return tuple(str(p) for p in paths)


@lru_cache(maxsize=4)
def _scan_person_index_files(vault_root_s: str) -> tuple[str, ...]:
    root = Path(vault_root_s)
    paths = sorted(p.resolve() for p in iter_person_index_paths(root))
    return tuple(str(p) for p in paths)


@lru_cache(maxsize=8)
def _load_vault_frontmatter(path_s: str) -> dict[str, Any]:
    """读一个人物索引 frontmatter，返回 {person, framework, display_name, id, skills[], rules[]}。"""
    try:
        text = Path(path_s).read_text(encoding="utf-8")
    except OSError:
        return {}
    fm, _body = parse_frontmatter(text)
    return fm if isinstance(fm, dict) else {}


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


def _person_index_record(agent_id: str, *, vault_root: Path | str | None = None) -> dict[str, Any] | None:
    """按 agent_id（人物名）在 Obsidian 人物索引中定位记录。"""
    root = vault_agent_root(vault_root)
    for path_s in _scan_person_index_files(str(root)):
        fm = _load_vault_frontmatter(path_s)
        pid = (fm.get("person") or "").strip()
        if pid and pid == agent_id:
            rec: dict[str, Any] = dict(fm)
            rec["_path"] = path_s
            rec["source"] = "person-index"
            return rec
        idx = (fm.get("id") or "")
        if idx and str(idx) == agent_id:
            rec = dict(fm)
            rec["_path"] = path_s
            rec["source"] = "person-index"
            return rec
    return None


def _merge_vault_profile(record: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    """person 索引 frontmatter 覆盖 profile.json 的 skills/rules（保留 archetype 等非技能字段）。"""
    merged = dict(record)
    skills = [s for s in index.get("skills") or [] if isinstance(s, dict)]
    rules = [r for r in index.get("rules") or [] if isinstance(r, dict)]
    merged["skills"] = skills
    merged["rules"] = rules
    if index.get("display_name"):
        merged["display_name"] = index["display_name"]
    if index.get("framework"):
        merged["framework"] = index["framework"]
    merged["_index_path"] = index.get("_path")
    return merged


def load_all_profiles(*, pack_root: Path | str | None = None, vault_root: Path | str | None = None, refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Return {agent_id: record}。skills/rules 优先取 Obsidian 人物索引，fallback profile.json。"""
    root = team_pack_root(pack_root)
    key = f"{root.resolve()}|{vault_agent_root(vault_root).resolve()}"
    if refresh:
        _PROFILE_CACHE.pop(key, None)
        _scan_profile_files.cache_clear()
        _scan_person_index_files.cache_clear()
        _load_vault_frontmatter.cache_clear()
    cached = _PROFILE_CACHE.get(key)
    if cached is not None:
        return cached

    profiles: dict[str, dict[str, Any]] = {}
    for path_s in _scan_profile_files(str(root)):
        record = load_profile_record(Path(path_s))
        if not record:
            continue
        aid = record["agent_id"]
        index = _person_index_record(aid, vault_root=vault_root)
        if index:
            record = _merge_vault_profile(record, index)
        if aid in profiles:
            raise ValueError(f"duplicate profile agent_id: {aid}")
        profiles[aid] = record
    _PROFILE_CACHE[key] = profiles
    return profiles


def get_profile(agent_id: str, *, pack_root: Path | str | None = None, vault_root: Path | str | None = None) -> dict[str, Any] | None:
    return load_all_profiles(pack_root=pack_root, vault_root=vault_root).get(agent_id)


def skill_paths_for_profile(agent_id: str, *, pack_root: Path | str | None = None, vault_root: Path | str | None = None) -> list[str]:
    """人物索引 `skills[].path` 优先；无则 profile.json skills[]。"""
    rec = get_profile(agent_id, pack_root=pack_root, vault_root=vault_root)
    if not rec:
        return []
    skills = rec.get("skills") or []
    if skills and isinstance(skills[0], dict):
        return [str(s.get("path")) for s in skills if isinstance(s, dict) and s.get("path")]
    return [s for s in skills if isinstance(s, str) and s.strip()]


def rule_paths_for_profile(agent_id: str, *, pack_root: Path | str | None = None, vault_root: Path | str | None = None) -> list[str]:
    """人物索引 `rules[].path` 优先；无则 profile.json rules[]。"""
    rec = get_profile(agent_id, pack_root=pack_root, vault_root=vault_root)
    if not rec:
        return []
    rules = rec.get("rules") or []
    if rules and isinstance(rules[0], dict):
        return [str(r.get("path")) for r in rules if isinstance(r, dict) and r.get("path")]
    return [r for r in rules if isinstance(r, str) and r.strip()]


def agent_archetypes(*, pack_root: Path | str | None = None, vault_root: Path | str | None = None) -> dict[str, str]:
    return {
        aid: rec["archetype"]
        for aid, rec in load_all_profiles(pack_root=pack_root, vault_root=vault_root).items()
        if rec.get("archetype")
    }
