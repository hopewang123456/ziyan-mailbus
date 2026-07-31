"""Phase 3.3 — registry-driven skill sync targets + rules mirror."""
from __future__ import annotations

from lib.adapters.clock import now_dt, now_ts, now_utc_dt
import platform
import re
import shutil
from pathlib import Path
from typing import Any, Iterator

from .agent_registry import (
    get_agent,
    hermes_sync_skills_dir,
    layer_skills_for_agent,
    load_all_agents,
)
from .constants import MAILBUS_ROOT, MAILBUS_ROOT_STR, MAILBUS_DATA_STR

_MNT_RE = re.compile(r"^/mnt/([a-zA-Z])/(.*)$")


def default_use_symlink() -> bool:
    """Windows symlink error 1920 — default to copy."""
    return platform.system() != "Windows"


def normalize_host_path(path_str: str, *, mail_root: Path | None = None) -> Path:
    """Convert /mnt/e/... or relative paths to native absolute Path."""
    root = Path(mail_root) if mail_root is not None else MAILBUS_ROOT
    ai_tools = root.parent
    raw = (path_str or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("empty path")
    m = _MNT_RE.match(raw)
    if m:
        drive = m.group(1).upper()
        tail = m.group(2).replace("/", "\\")
        return Path(f"{drive}:/") / tail
    if raw.startswith("mailbus-core/"):
        return root / raw[len("mailbus-core/"):]
    if raw.startswith("team-pack/"):
        from .constants import TEAM_PACK_ROOT
        return TEAM_PACK_ROOT / raw[len("team-pack/"):]
    if raw.startswith("mail/"):
        return root / raw.replace("mail/", "", 1)
    p = Path(raw)
    if p.is_absolute():
        return p
    return ai_tools / raw


def workspace_skills_root(agent_rec: dict[str, Any], *, mail_root: Path | None = None) -> Path | None:
    """Host path for framework workspace skills/ (opencode, openclaw)."""
    ws = agent_rec.get("workspace")
    if not ws:
        return None
    fw = agent_rec.get("framework") or ""
    if fw not in ("opencode", "openclaw"):
        return None
    host = normalize_host_path(str(ws), mail_root=mail_root)
    return host / "skills"


def sync_target_for_agent(
    agent_id: str,
    *,
    mail_root: Path | None = None,
) -> tuple[str, Path | None]:
    """Return (framework, skills_target_path). None target → dedicated sync script."""
    rec = get_agent(agent_id, mail_root=mail_root)
    if not rec:
        return ("unknown", None)
    fw = (rec.get("framework") or "").strip()
    if fw == "hermes_profile":
        return (fw, hermes_sync_skills_dir(agent_id, mail_root=mail_root))
    if fw in ("claude_code", "codex"):
        return (fw, None)
    target = workspace_skills_root(rec, mail_root=mail_root)
    return (fw, target)


def iter_syncable_agents(*, mail_root: Path | None = None) -> Iterator[tuple[str, str, Path | None]]:
    """Yield (agent_id, framework, target_path) for all registry agents."""
    for agent_id in sorted(load_all_agents(mail_root=mail_root)):
        fw, target = sync_target_for_agent(agent_id, mail_root=mail_root)
        yield agent_id, fw, target


def _is_reparse_or_symlink(path: Path) -> bool:
    if path.is_symlink():
        return True
    if platform.system() == "Windows":
        try:
            import ctypes

            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            if attrs == -1:
                return False
            return bool(attrs & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
        except Exception:
            return False
    return False


def _link_dir(link: Path, target: Path) -> None:
    """Create directory junction (Windows) or symlink (POSIX) link -> target."""
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        if _is_reparse_or_symlink(link):
            if platform.system() == "Windows":
                import subprocess

                subprocess.run(["cmd", "/c", "rmdir", str(link)], check=False, capture_output=True)
            else:
                link.unlink()
        else:
            raise RuntimeError(f"Refusing to replace real directory: {link}")
    target = target.resolve()
    if platform.system() == "Windows":
        import subprocess

        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode != 0:
            # fallback: pathlib symlink (needs privilege) or raise
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                raise RuntimeError(f"junction failed: {r.stderr or r.stdout or exc}") from exc
    else:
        link.symlink_to(target, target_is_directory=True)


def mirror_rules_to_store(data_dir: str | Path, *, mail_root: Path | None = None) -> list[str]:
    """Ensure store/rules → Vault MAILBUS_RULES_ROOT (junction/symlink), no copy.

    team-pack rules stay at TEAM_PACK_RULES_ROOT (already Vault-mounted on host).
    Local: Obsidian is the only md SoT; store/rules is a mount point.
    """
    from .constants import MAILBUS_RULES_ROOT, TEAM_PACK_RULES_ROOT

    if mail_root is not None:
        # Prefer resolved Vault root when mail/rules is itself a junction
        sot = (Path(mail_root) / "rules").resolve()
    else:
        sot = MAILBUS_RULES_ROOT.resolve()

    dest = Path(data_dir) / "rules"
    linked: list[str] = []

    if not sot.is_dir():
        raise FileNotFoundError(f"rules SoT missing: {sot}")

    need_link = True
    if dest.exists() or dest.is_symlink():
        if _is_reparse_or_symlink(dest):
            try:
                if dest.resolve() == sot:
                    need_link = False
            except Exception:
                need_link = True
        else:
            # Real directory leftover — back up once, then link
            bak = Path(str(dest) + ".__pre-vault")
            if bak.exists():
                shutil.rmtree(bak, ignore_errors=True)
            dest.rename(bak)

    if need_link:
        if dest.exists() or dest.is_symlink():
            if _is_reparse_or_symlink(dest):
                if platform.system() == "Windows":
                    import subprocess

                    subprocess.run(["cmd", "/c", "rmdir", str(dest)], check=False, capture_output=True)
                else:
                    dest.unlink(missing_ok=True)
            else:
                raise RuntimeError(f"store/rules still a real dir: {dest}")
        _link_dir(dest, sot)

    # Report reachable md files (SoT), not copied count
    for src in sorted(sot.rglob("*.md")):
        linked.append(src.relative_to(sot).as_posix())
    # team-pack remains separate SoT
    if TEAM_PACK_RULES_ROOT.is_dir():
        linked.append(f"(team-pack SoT) {TEAM_PACK_RULES_ROOT}")
    return linked


def build_skills_index_from_registry(
    *,
    mail_root: Path | str | None = None,
    existing_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build skills-index agents{} from team-pack profiles + transport registry."""
    from datetime import datetime, timezone

    index: dict[str, Any] = dict(existing_index or {})
    agents_out: dict[str, Any] = {}
    registry = load_all_agents(mail_root=mail_root, refresh=True)

    LAYER_TYPES = frozenset({
        "shared_skill",
        "framework_skill",
        "role_archetype",
        "role_overlay",
    })

    for agent_id in sorted(registry):
        rec = registry[agent_id]
        fw = (rec.get("framework") or "").strip()
        archetype = (rec.get("archetype") or "").strip()
        layer_specs = layer_skills_for_agent(agent_id, fw, mail_root=mail_root)
        layer_keys = {f"{s.get('type')}:{s.get('id')}" for s in layer_specs}

        old_entry = ((index.get("agents") or {}).get(agent_id) or {})
        old_skills = old_entry.get("skills") or []
        rest = []
        for item in old_skills:
            if not isinstance(item, dict):
                continue
            k = f"{item.get('type')}:{item.get('id')}"
            if k in layer_keys or item.get("type") in LAYER_TYPES:
                continue
            rest.append(item)

        agents_out[agent_id] = {
            "framework": fw,
            "archetype": archetype,
            "skills": layer_specs + rest,
        }

    index["agents"] = agents_out
    index["updated_at"] = now_utc_dt().strftime("%Y-%m-%d")
    index["schema"] = index.get("schema") or "skills-index-v2"
    index["source"] = "team-pack/profiles + access/transport"
    return index


def host_skills_dir_for_agent(agent_id: str, *, mail_root: Path | None = None) -> Path | None:
    """Resolve host skills directory for Dashboard / skill-use scans."""
    fw, target = sync_target_for_agent(agent_id, mail_root=mail_root)
    if target is not None:
        return target
    rec = get_agent(agent_id, mail_root=mail_root) or {}
    if fw == "claude_code":
        try:
            from .claude_launch import load_mailbus_claude, resolve_claude_home, resolve_claude_plat_cfg

            plat, plat_cfg = resolve_claude_plat_cfg(load_mailbus_claude())
            home = Path(resolve_claude_home(plat_cfg, agent_id))
            return home / "skills"
        except Exception:
            return None
    if fw == "codex":
        import os

        codex_home = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
        return Path(codex_home) / "skills"
    return None


def dashboard_skills_dirs(*, mail_root: Path | None = None) -> dict[str, str]:
    """agent_id → host skills dir for Dashboard registry (#2)."""
    out: dict[str, str] = {}
    for agent_id in sorted(load_all_agents(mail_root=mail_root)):
        p = host_skills_dir_for_agent(agent_id, mail_root=mail_root)
        if p is not None:
            out[agent_id] = str(p)
    return out
