"""Planner RAG — SQLite FTS5 索引与检索。"""

from __future__ import annotations

import os
import sqlite3
from typing import List

from ...utils import _now_iso
from .sources import iter_source_chunks, mailbus_root


def _db_path(data_dir: str, cfg: dict) -> str:
    rel = ((cfg.get("rag") or {}).get("index") or {}).get("path") or "store/rag/mailbus-planner.sqlite"
    root = mailbus_root(data_dir)
    if rel.startswith("store/"):
        return os.path.join(root, rel.replace("/", os.sep))
    return os.path.join(data_dir, rel.replace("/", os.sep))


def _conn(data_dir: str, cfg: dict) -> sqlite3.Connection:
    path = _db_path(data_dir, cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS planner_rag USING fts5(
            doc_id UNINDEXED,
            source_id,
            title,
            body,
            path UNINDEXED,
            priority UNINDEXED,
            tokenize='unicode61'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS planner_rag_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    return conn


def rebuild_index(data_dir: str, cfg: dict) -> int:
    rag = cfg.get("rag") or {}
    max_chars = int(rag.get("max_chars_per_chunk") or 800)
    sources = rag.get("sources") or []
    conn = _conn(data_dir, cfg)
    try:
        conn.execute("DELETE FROM planner_rag")
        count = 0
        for src in sources:
            for chunk in iter_source_chunks(data_dir, src, max_chars=max_chars):
                doc_id = f"{chunk['source_id']}:{chunk['chunk_index']}:{chunk['title']}"
                conn.execute(
                    """INSERT INTO planner_rag (doc_id, source_id, title, body, path, priority)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (doc_id, chunk["source_id"], chunk["title"], chunk["body"],
                     chunk["path"], chunk["priority"]),
                )
                count += 1
        conn.execute(
            "INSERT OR REPLACE INTO planner_rag_meta (key, value) VALUES (?, ?)",
            ("rebuilt_at", _now_iso()),
        )
        conn.commit()
        return count
    finally:
        conn.close()


def retrieve(data_dir: str, cfg: dict, query: str, *, top_k: int = 8) -> List[dict]:
    rag = cfg.get("rag") or {}
    if not rag.get("enabled", True):
        return []
    max_k = int(rag.get("max_chunks") or top_k)
    top_k = min(top_k, max_k)

    conn = _conn(data_dir, cfg)
    try:
        n = conn.execute("SELECT COUNT(*) FROM planner_rag").fetchone()[0]
        if n == 0:
            rebuild_index(data_dir, cfg)
        q = query.replace('"', ' ').strip() or "role flow task"
        rows = conn.execute(
            """SELECT doc_id, source_id, title, body, path, priority
               FROM planner_rag
               WHERE planner_rag MATCH ?
               ORDER BY rank, priority DESC
               LIMIT ?""",
            (q, top_k),
        ).fetchall()
        if not rows:
            rows = conn.execute(
                """SELECT doc_id, source_id, title, body, path, priority
                   FROM planner_rag ORDER BY priority DESC LIMIT ?""",
                (top_k,),
            ).fetchall()
        return [
            {
                "source_id": r["source_id"],
                "title": r["title"],
                "excerpt": (r["body"] or "")[:300],
                "path": r["path"],
            }
            for r in rows
        ]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def index_info(data_dir: str, cfg: dict) -> dict:
    path = _db_path(data_dir, cfg)
    rag = cfg.get("rag") or {}
    sources = rag.get("sources") or []
    info = {
        "path": path,
        "exists": os.path.isfile(path),
        "chunks": 0,
        "rebuilt_at": None,
        "source_count": len(sources),
        "sources": [
            {
                "id": s.get("id") or s.get("source_id") or f"src{i}",
                "path": s.get("path") or "",
                "priority": s.get("priority", 0),
            }
            for i, s in enumerate(sources)
            if isinstance(s, dict)
        ],
    }
    if not info["exists"]:
        return info
    conn = _conn(data_dir, cfg)
    try:
        info["chunks"] = conn.execute("SELECT COUNT(*) FROM planner_rag").fetchone()[0]
        row = conn.execute(
            "SELECT value FROM planner_rag_meta WHERE key='rebuilt_at'"
        ).fetchone()
        if row:
            info["rebuilt_at"] = row[0]
    finally:
        conn.close()
    return info
