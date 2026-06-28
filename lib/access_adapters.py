"""Framework adapter metadata — load from mail/access/{fw}/adapter/ (Phase 3.4)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .agent_registry import list_agents_by_framework, load_all_agents
from .constants import MAILBUS_ROOT

# agent.json framework → access/ subdirectory
FRAMEWORK_ACCESS_DIR: dict[str, str] = {
    "hermes_profile": "hermes",
    "hermes": "hermes",
    "codex": "codex",
    "claude_code": "claude_code",
    "opencode": "opencode",
    "openclaw": "openclaw",
    "cline": "cline",
    "cursor": "cursor",
}


def mailbus_root(mail_root: Path | str | None = None) -> Path:
    return Path(mail_root) if mail_root is not None else MAILBUS_ROOT


def access_subdir_for_framework(framework: str) -> str:
    fw = (framework or "").strip()
    return FRAMEWORK_ACCESS_DIR.get(fw, fw)


def access_root_for_framework(framework: str, *, mail_root: Path | None = None) -> Path:
    root = mailbus_root(mail_root)
    return root / "access" / access_subdir_for_framework(framework)


def adapter_dir_for_framework(framework: str, *, mail_root: Path | None = None) -> Path:
    return access_root_for_framework(framework, mail_root=mail_root) / "adapter"


def adapter_spec_path(framework: str, *, mail_root: Path | None = None) -> Path:
    return adapter_dir_for_framework(framework, mail_root=mail_root) / "SPEC.md"


def load_adapter_spec(framework: str, *, mail_root: Path | None = None) -> str:
    path = adapter_spec_path(framework, mail_root=mail_root)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    legacy = mailbus_root(mail_root) / "adapters" / framework / "framework-runtime" / "SKILL.md"
    if legacy.is_file():
        return legacy.read_text(encoding="utf-8")
    return ""


@lru_cache(maxsize=1)
def _frameworks_with_adapter_spec() -> frozenset[str]:
    found: set[str] = set()
    access = MAILBUS_ROOT / "access"
    if not access.is_dir():
        return frozenset()
    for fw_dir, sub in FRAMEWORK_ACCESS_DIR.items():
        spec = access / sub / "adapter" / "SPEC.md"
        if spec.is_file():
            found.add(fw_dir)
    return frozenset(found)


def adapter_spec_available(framework: str) -> bool:
    return framework in _frameworks_with_adapter_spec() or adapter_spec_path(framework).is_file()


def agents_for_framework(framework: str, *, mail_root: Path | None = None) -> list[str]:
    return list_agents_by_framework(framework, mail_root=mail_root)


def validate_access_adapters(*, mail_root: Path | None = None) -> list[str]:
    """Ensure each registry framework has access/adapter/SPEC.md."""
    errors: list[str] = []
    frameworks = sorted({rec.get("framework") for rec in load_all_agents(mail_root=mail_root).values() if rec.get("framework")})
    for fw in frameworks:
        if fw == "none":
            continue
        spec = adapter_spec_path(fw, mail_root=mail_root)
        if not spec.is_file():
            errors.append(f"missing access adapter spec: {spec}")
    return errors
