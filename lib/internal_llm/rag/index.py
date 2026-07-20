"""Lightweight RAG index for Internal LLM Planner.

Indexes configured text/json sources into a JSON chunk store and does
simple keyword retrieval. Enough for dry-run / require_rag_citations;
can be replaced by sqlite_fts later.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _root_and_index_path(data_dir: str, cfg: dict | None) -> tuple[Path, Path]:
    data = Path(data_dir).resolve()
    mail_root = data.parent if data.name == "store" else data
    rag = (cfg or {}).get("rag") or {}
    idx = rag.get("index") or {}
    rel = (idx.get("path") or "store/rag/mailbus-planner.sqlite").replace("\\", "/")
    # Prefer sibling JSON next to configured sqlite path
    if rel.endswith(".sqlite"):
        rel = rel[: -len(".sqlite")] + ".chunks.json"
    elif not rel.endswith(".json"):
        rel = rel.rstrip("/") + "/chunks.json"
    # paths in config are often "store/..." relative to mail root
    if rel.startswith("store/"):
        index_path = mail_root / rel
    else:
        index_path = data / rel
    return mail_root, index_path


def _load_chunks(index_path: Path) -> list[dict]:
    if not index_path.is_file():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return list(data.get("chunks") or [])
    except (OSError, json.JSONDecodeError):
        return []


def _chunk_text(text: str, max_chars: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    i = 0
    while i < len(text):
        parts.append(text[i : i + max_chars])
        i += max_chars
    return parts


def _read_source(mail_root: Path, data_dir: Path, src: dict) -> list[tuple[str, str, str]]:
    """Return list of (source_id, title, text)."""
    sid = src.get("id") or "src"
    raw_path = (src.get("path") or "").replace("\\", "/")
    if not raw_path:
        return []
    if raw_path.startswith("store/"):
        path = mail_root / raw_path
    elif Path(raw_path).is_absolute():
        path = Path(raw_path)
    else:
        # identities etc relative to mail root
        cand = mail_root / raw_path
        path = cand if cand.exists() else data_dir / raw_path

    out: list[tuple[str, str, str]] = []
    glob_pat = src.get("glob")
    if path.is_dir() and glob_pat:
        for fp in sorted(path.glob(glob_pat)):
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            out.append((sid, fp.name, text))
        return out
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return [(sid, path.name, text)]


def index_info(data_dir: str, cfg: dict | None = None) -> dict[str, Any]:
    _, index_path = _root_and_index_path(data_dir, cfg)
    chunks = _load_chunks(index_path)
    return {"chunks": len(chunks), "enabled": True, "path": str(index_path)}


def rebuild_index(data_dir: str, cfg: dict | None = None) -> int:
    cfg = cfg or {}
    mail_root, index_path = _root_and_index_path(data_dir, cfg)
    data = Path(data_dir).resolve()
    rag = cfg.get("rag") or {}
    max_chars = int(rag.get("max_chars_per_chunk") or 800)
    sources = list(rag.get("sources") or [])
    chunks: list[dict] = []
    for src in sources:
        for sid, title, text in _read_source(mail_root, data, src):
            for i, piece in enumerate(_chunk_text(text, max_chars)):
                chunks.append(
                    {
                        "source_id": sid,
                        "title": title,
                        "excerpt": piece,
                        "priority": int(src.get("priority") or 50),
                        "chunk_id": f"{sid}:{title}:{i}",
                    }
                )
    index_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"chunks": chunks, "count": len(chunks)}
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(chunks)


def retrieve(
    data_dir: str,
    cfg: dict | None,
    query: str,
    *,
    top_k: int = 8,
) -> list[dict]:
    cfg = cfg or {}
    rag = cfg.get("rag") or {}
    if not rag.get("enabled", True):
        return []
    _, index_path = _root_and_index_path(data_dir, cfg)
    chunks = _load_chunks(index_path)
    if not chunks:
        # lazy rebuild once if empty
        rebuild_index(data_dir, cfg)
        chunks = _load_chunks(index_path)
    if not chunks:
        return []

    tokens = [t for t in re.split(r"[\s\W_]+", (query or "").lower()) if len(t) >= 2]
    if not tokens:
        tokens = [(query or "").lower()[:32]] if query else []

    scored: list[tuple[float, dict]] = []
    for ch in chunks:
        hay = f"{ch.get('title','')} {ch.get('excerpt','')}".lower()
        hit = sum(1 for t in tokens if t and t in hay)
        score = hit * 10 + float(ch.get("priority") or 0) / 100.0
        if hit or not tokens:
            scored.append((score, ch))
    scored.sort(key=lambda x: (-x[0], -float(x[1].get("priority") or 0)))
    limit = int(top_k or rag.get("max_chunks") or 8)
    out = []
    for score, ch in scored[:limit]:
        out.append(
            {
                "source_id": ch.get("source_id"),
                "title": ch.get("title") or "",
                "excerpt": (ch.get("excerpt") or "")[:240],
                "score": score,
            }
        )
    # if keyword miss, still return top priority chunks so citations exist
    if not out:
        top = sorted(chunks, key=lambda c: -int(c.get("priority") or 0))[:limit]
        for ch in top:
            out.append(
                {
                    "source_id": ch.get("source_id"),
                    "title": ch.get("title") or "",
                    "excerpt": (ch.get("excerpt") or "")[:240],
                    "score": 0.0,
                }
            )
    return out
