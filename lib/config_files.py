"""Config path helpers — runtime always binds non-example files.

``.example.json`` files are for humans to copy after clone; they are never the
silent production SoT for business loaders.
"""
from __future__ import annotations

import shutil
import warnings
from pathlib import Path
from typing import NamedTuple


class ConfigResolveResult(NamedTuple):
    path: Path | None
    """Resolved real config path, or None if missing."""
    hint: str
    """Copy hint when missing (mentions sibling .example if present)."""


def is_example_config_name(name: str) -> bool:
    """True if filename is an example/template seed, not a runtime bind target."""
    n = name.lower()
    return (
        n.endswith(".example.json")
        or ".example." in n
        or n.endswith(".template.json")
        or n.endswith(".schema.json")
    )


def example_sibling(real_path: Path | str) -> Path:
    """``foo.json`` → ``foo.example.json`` (same directory)."""
    p = Path(real_path)
    return p.with_name(f"{p.stem}.example{p.suffix}")


def resolve_config_path(real_path: Path | str) -> ConfigResolveResult:
    """Resolve a runtime config path.

    Only returns ``real_path`` when that file exists. Never returns ``*.example.json``
    as the bound config. If missing, ``hint`` tells the user to copy the example.
    """
    path = Path(real_path)
    if is_example_config_name(path.name):
        raise ValueError(
            f"runtime config path must not be an example file: {path}. "
            f"Use {path.name.replace('.example', '', 1)} after copying."
        )
    if path.is_file():
        return ConfigResolveResult(path, "")
    ex = example_sibling(path)
    if ex.is_file():
        hint = (
            f"missing {path.name}; copy {ex.name} → {path.name} and fill in your values"
        )
    else:
        hint = f"missing {path} (no {ex.name} either)"
    return ConfigResolveResult(None, hint)


def require_config_path(real_path: Path | str) -> Path:
    """Like resolve_config_path but raises FileNotFoundError with copy hint."""
    res = resolve_config_path(real_path)
    if res.path is None:
        raise FileNotFoundError(res.hint or f"missing config: {real_path}")
    return res.path


def materialize_from_example(real_path: Path | str, *, overwrite: bool = False) -> Path | None:
    """Copy ``foo.example.json`` → ``foo.json`` if real file missing (or overwrite).

    Returns the real path if created/present, else None when no example exists.
    """
    path = Path(real_path)
    if path.is_file() and not overwrite:
        return path
    ex = example_sibling(path)
    if not ex.is_file():
        return path if path.is_file() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and not overwrite:
        return path
    shutil.copy2(ex, path)
    return path


def iter_runtime_json_files(directory: Path | str, *, pattern: str = "*.json") -> list[Path]:
    """List JSON files under directory, skipping example/template/schema seeds."""
    root = Path(directory)
    if not root.is_dir():
        return []
    out: list[Path] = []
    for path in sorted(root.glob(pattern)):
        if not path.is_file():
            continue
        if is_example_config_name(path.name):
            continue
        out.append(path)
    return out


def ensure_sensitive_config_files(mail_root: Path | str | None = None) -> list[str]:
    """Materialize known sensitive configs from *.example.json when real file missing.

    Never overwrites existing local files. Returns list of created relative paths.
    """
    root = Path(mail_root) if mail_root else Path(__file__).resolve().parent.parent
    created: list[str] = []
    pairs = [
        root / "config" / "mailbus" / "launch-ports.json",
        root / "access" / "external-tools" / "registry.json",
        root / "access" / "external-tools" / "grants.json",
    ]
    for real in pairs:
        before = real.is_file()
        out = materialize_from_example(real, overwrite=False)
        if out is not None and out.is_file() and not before:
            try:
                created.append(str(out.relative_to(root)))
            except ValueError:
                created.append(str(out))
    return created


def warn_if_missing(real_path: Path | str) -> None:
    res = resolve_config_path(real_path)
    if res.path is None and res.hint:
        warnings.warn(res.hint, UserWarning, stacklevel=2)
