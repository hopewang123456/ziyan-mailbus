"""Rules registry — merge common + framework + role rules per agent."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .agent_registry import get_agent, mailbus_root
from .constants import MAILBUS_ROOT

# Default common rules when agent.json omits explicit rules[].
DEFAULT_COMMON_RULES: tuple[str, ...] = (
    "mail/rules/common/execution-order.md",
    "mail/rules/common/task-fsm.md",
    "mail/rules/common/team-secrets-policy.md",
)


def _norm_rel(path: str) -> str:
    return (path or "").replace("\\", "/").strip()


def default_rule_paths(archetype: str, framework: str) -> list[str]:
    """Derive rule paths from archetype + framework (no agent.json rules[])."""
    archetype = (archetype or "").strip()
    framework = (framework or "").strip()
    paths: list[str] = list(DEFAULT_COMMON_RULES)
    if framework:
        paths.append(f"mail/rules/frameworks/{framework}/delivery.md")
    if archetype:
        paths.append(f"mail/rules/roles/{archetype}/boundaries.md")
    return paths


def explicit_rule_paths(agent_id: str, *, mail_root: Path | str | None = None) -> list[str] | None:
    rec = get_agent(agent_id, mail_root=mail_root)
    if not rec:
        return None
    rules = rec.get("rules")
    if not isinstance(rules, list) or not rules:
        return None
    out: list[str] = []
    for item in rules:
        if isinstance(item, str) and item.strip():
            out.append(_norm_rel(item))
    return out or None


def rule_paths_for_agent(agent_id: str, *, mail_root: Path | str | None = None) -> list[str]:
    """Return ordered unique mail/rules/... relative paths for one agent."""
    rec = get_agent(agent_id, mail_root=mail_root)
    if not rec:
        return []
    explicit = explicit_rule_paths(agent_id, mail_root=mail_root)
    if explicit is not None:
        rels = explicit
    else:
        rels = default_rule_paths(rec.get("archetype", ""), rec.get("framework", ""))
    return _dedupe_preserve_order(rels)


def resolve_rule_path(rel: str, *, mail_root: Path | str | None = None) -> Path:
    root = mailbus_root(mail_root)
    rel = _norm_rel(rel)
    if rel.startswith("mail/rules/"):
        return root / rel.replace("mail/", "", 1)
    if rel.startswith("rules/"):
        return root / rel
    p = Path(rel)
    return p if p.is_absolute() else root / "rules" / rel.lstrip("/")


def resolved_rule_paths(agent_id: str, *, mail_root: Path | str | None = None, existing_only: bool = False) -> list[Path]:
    """Absolute paths to rule files for agent_id."""
    out: list[Path] = []
    for rel in rule_paths_for_agent(agent_id, mail_root=mail_root):
        path = resolve_rule_path(rel, mail_root=mail_root)
        if existing_only and not path.is_file():
            continue
        out.append(path)
    return out


def merge_rule_contents(agent_id: str, *, mail_root: Path | str | None = None) -> str:
    """Concatenate rule markdown for push/sync notifications."""
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
    """Group rule rel paths by layer: common / frameworks / roles."""
    grouped: dict[str, list[str]] = {"common": [], "frameworks": [], "roles": []}
    for rel in rule_paths_for_agent(agent_id, mail_root=mail_root):
        norm = _norm_rel(rel)
        if "/rules/common/" in norm:
            grouped["common"].append(norm)
        elif "/rules/frameworks/" in norm:
            grouped["frameworks"].append(norm)
        elif "/rules/roles/" in norm:
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
