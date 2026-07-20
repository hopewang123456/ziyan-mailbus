"""team-memory.db 写入 — schema 与 hermes-data/.hermes/scripts/memory.py 对齐。"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Optional

DEFAULT_TEAM_MEMORY_DB = (
    "/hermes/shared-memory/team-memory.db"
    if os.path.exists("/.dockerenv")
    else "/mnt/e/hermes-data/.hermes/shared-memory/team-memory.db"
)


def team_memory_db_path() -> str:
    return os.environ.get("TEAM_MEMORY_DB", DEFAULT_TEAM_MEMORY_DB)


def is_available() -> bool:
    """数据库目录可写且可打开。"""
    path = team_memory_db_path()
    parent = os.path.dirname(path) or "."
    try:
        os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.close()
        return True
    except OSError:
        return False


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            key TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            author TEXT DEFAULT '',
            created_at REAL DEFAULT (julianday('now')),
            updated_at REAL DEFAULT (julianday('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            key, content, category,
            content='memories', content_rowid='rowid'
        )
        """
    )


def _rebuild_fts(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("INSERT INTO memories_fts(memories) VALUES('rebuild')")
    except sqlite3.Error:
        pass


def store_memory(
    key: str,
    content: str,
    *,
    category: str = "general",
    author: str = "",
    db_path: Optional[str] = None,
) -> bool:
    """写入或更新一条记忆；key 唯一，天然幂等。"""
    path = db_path or team_memory_db_path()
    parent = os.path.dirname(path) or "."
    try:
        os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(path)
        _ensure_schema(conn)
        now = time.time()
        existing = conn.execute("SELECT key FROM memories WHERE key=?", (key,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE memories SET content=?, category=?, author=?, updated_at=? WHERE key=?",
                (content, category, author, now, key),
            )
        else:
            conn.execute(
                "INSERT INTO memories (key, content, category, author, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (key, content, category, author, now, now),
            )
        conn.commit()
        _rebuild_fts(conn)
        conn.commit()
        conn.close()
        return True
    except (OSError, sqlite3.Error):
        return False


def mailbus_message_key(msg_id: str) -> str:
    return f"mailbus:{msg_id}"


def format_mailbus_content(
    agent: str,
    from_agent: str,
    msg_type: str,
    content: str,
    *,
    max_len: int = 4000,
) -> str:
    body = content[:max_len]
    return f"[agent:{agent}] [from:{from_agent}] [type:{msg_type}] {body}"
