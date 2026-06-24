"""RAG 白名单源 — 切块供 Planner 检索。"""

from __future__ import annotations

import glob
import json
import os
from typing import Iterator

from ...utils import json_read


def mailbus_root(data_dir: str) -> str:
    if os.path.basename(os.path.normpath(data_dir)) == "store":
        return os.path.dirname(os.path.normpath(data_dir))
    return data_dir


def _resolve_path(data_dir: str, rel: str) -> str:
    root = mailbus_root(data_dir)
    if rel.startswith("store/"):
        return os.path.join(root, rel.replace("/", os.sep))
    return os.path.join(root, rel.replace("/", os.sep))


def iter_source_chunks(data_dir: str, source: dict, *, max_chars: int = 800) -> Iterator[dict]:
    """yield {source_id, title, body, path, priority}."""
    sid = source.get("id") or "unknown"
    priority = int(source.get("priority") or 50)
    rel = source.get("path") or ""
    if not rel:
        return

    base = _resolve_path(data_dir, rel)
    gpat = source.get("glob")
    paths = []
    if gpat and os.path.isdir(base):
        paths = sorted(glob.glob(os.path.join(base, gpat)))
    elif os.path.isfile(base):
        paths = [base]
    elif os.path.isdir(base):
        paths = sorted(glob.glob(os.path.join(base, "**", "*"), recursive=True))
        paths = [p for p in paths if os.path.isfile(p) and not p.endswith(".pyc")][:20]

    for path in paths:
        try:
            if path.endswith(".json"):
                raw = json.dumps(json_read(path, {}), ensure_ascii=False, indent=0)
            else:
                with open(path, encoding="utf-8", errors="replace") as f:
                    raw = f.read()
        except OSError:
            continue
        if not raw.strip():
            continue
        for i in range(0, len(raw), max_chars):
            chunk = raw[i: i + max_chars]
            yield {
                "source_id": sid,
                "title": os.path.basename(path),
                "body": chunk,
                "path": path,
                "priority": priority,
                "chunk_index": i // max_chars,
            }
