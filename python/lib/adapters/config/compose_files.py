"""Compose YAML 文件柜：仅 list/read/write，无 docker compose 启停。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+\.ya?ml$", re.I)


def compose_roots(mailbus_root: str | Path) -> list[Path]:
    root = Path(mailbus_root).resolve()
    return [root / "docker-agents", root]


def _resolve_under_roots(mailbus_root: str | Path, rel: str) -> Path:
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("invalid compose path")
    name = Path(rel).name
    if not _SAFE_NAME.match(name):
        raise ValueError("compose file must be *.yml / *.yaml with safe name")
    root = Path(mailbus_root).resolve()
    candidate = (root / rel).resolve()
    allowed = False
    for base in compose_roots(root):
        try:
            candidate.relative_to(base.resolve())
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        raise ValueError("compose path outside allowed roots")
    return candidate


def list_compose_files(mailbus_root: str | Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    root = Path(mailbus_root).resolve()
    for base in compose_roots(root):
        if not base.is_dir():
            continue
        for p in sorted(base.glob("docker-compose*.yml")) + sorted(base.glob("docker-compose*.yaml")):
            try:
                rel = str(p.resolve().relative_to(root)).replace("\\", "/")
            except ValueError:
                continue
            if rel in seen:
                continue
            seen.add(rel)
            items.append({
                "path": rel,
                "name": p.name,
                "size": p.stat().st_size if p.is_file() else 0,
            })
    return items


def read_compose_file(mailbus_root: str | Path, rel: str) -> dict[str, Any]:
    path = _resolve_under_roots(mailbus_root, rel)
    if not path.is_file():
        raise FileNotFoundError(rel)
    text = path.read_text(encoding="utf-8")
    return {"path": rel.replace("\\", "/"), "content": text}


def write_compose_file(mailbus_root: str | Path, rel: str, content: str) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ValueError("content must be string")
    path = _resolve_under_roots(mailbus_root, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return {"path": rel.replace("\\", "/"), "bytes": len(content.encode("utf-8")), "saved": True}
