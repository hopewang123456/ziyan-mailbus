"""Rules registry — merge common + framework + role rules per agent."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .agent_registry import get_agent, mailbus_root
from lib.infra.constants import AGENT_VAULT_ROOT, MAILBUS_RULES_ROOT, TEAM_PACK_RULES_ROOT
from .profile_registry import get_profile, rule_paths_for_profile

DEFAULT_COMMON_RULES: tuple[str, ...] = (
    "01-mailbus/011-rule/0111-common/execution-order",
    "01-mailbus/011-rule/0111-common/task-fsm",
    "01-mailbus/011-rule/0111-common/team-secrets-policy",
)


def _norm_rel(path: str) -> str:
    return (path or "").replace("\\", "/").strip()


def default_rule_paths(archetype: str, framework: str) -> list[str]:
    archetype = (archetype or "").strip()
    framework = (framework or "").strip()
    paths: list[str] = list(DEFAULT_COMMON_RULES)
    if framework:
        paths.append(f"01-mailbus/011-rule/0112-frameworks/{framework}/delivery")
    if archetype:
        paths.append(f"01-mailbus/014-team/0141-positions/{archetype}/boundaries")
    return paths


def explicit_rule_paths(agent_id: str, *, mail_root: Path | str | None = None) -> list[str] | None:
    rules = rule_paths_for_profile(agent_id)
    if not rules:
        return None
    out: list[str] = []
    for item in rules:
        if isinstance(item, str) and item.strip():
            out.append(_norm_rel(item))
    return out or None


def rule_paths_for_agent(agent_id: str, *, mail_root: Path | str | None = None) -> list[str]:
    rec = get_agent(agent_id, mail_root=mail_root)
    if not rec:
        return []
    explicit = explicit_rule_paths(agent_id, mail_root=mail_root)
    if explicit is not None:
        rels = explicit
    else:
        prof = get_profile(agent_id) or {}
        rels = default_rule_paths(prof.get("archetype", ""), rec.get("framework", ""))
    return _dedupe_preserve_order(rels)


def resolve_rule_path(rel: str, *, mail_root: Path | str | None = None) -> Path:
    rules = MAILBUS_RULES_ROOT
    pack_rules = TEAM_PACK_RULES_ROOT
    vault = AGENT_VAULT_ROOT
    rel = _norm_rel(rel)
    if rel.startswith("01-mailbus/") or rel.startswith("02-members/") or rel.startswith("03-shared/"):
        p = vault / rel
        if p.is_file() or p.suffix == ".md":
            return p
        return p.with_suffix(".md")
    if rel.startswith("mailbus-core/rules/"):
        return rules / rel[len("mailbus-core/rules/"):]
    if rel.startswith("team-pack/rules/"):
        return pack_rules / rel[len("team-pack/rules/"):]
    if rel.startswith("mail/rules/"):
        tail = rel[len("mail/rules/"):]
        if tail.startswith("roles/"):
            return pack_rules / tail
        return rules / tail
    if rel.startswith("rules/"):
        return rules / rel[len("rules/"):]
    p = Path(rel)
    return p if p.is_absolute() else rules / rel.lstrip("/")


def resolved_rule_paths(agent_id: str, *, mail_root: Path | str | None = None, existing_only: bool = False) -> list[Path]:
    out: list[Path] = []
    for rel in rule_paths_for_agent(agent_id, mail_root=mail_root):
        path = resolve_rule_path(rel, mail_root=mail_root)
        if existing_only and not path.is_file():
            continue
        out.append(path)
    return out


def merge_rule_contents(agent_id: str, *, mail_root: Path | str | None = None) -> str:
    parts: list[str] = []
    for path in resolved_rule_paths(agent_id, mail_root=mail_root, existing_only=True):
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            parts.append(f"<!-- rule: {path.name} -->\n{text}")
    return "\n\n---\n\n".join(parts)


def rules_by_layer(agent_id: str, *, mail_root: Path | str | None = None) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {"common": [], "frameworks": [], "roles": []}
    for rel in rule_paths_for_agent(agent_id, mail_root=mail_root):
        norm = _norm_rel(rel)
        if "/0111-common/" in norm or "/rules/common/" in norm:
            grouped["common"].append(norm)
        elif "/0112-frameworks/" in norm or "/rules/frameworks/" in norm:
            grouped["frameworks"].append(norm)
        elif "/0141-positions/" in norm or "/rules/roles/" in norm:
            grouped["roles"].append(norm)
    return grouped


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = _norm_rel(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out
