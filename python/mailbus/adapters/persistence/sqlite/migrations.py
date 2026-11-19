"""schema 版本与迁移执行。

约定：迁移文件 ``NNN_name.sql``；只允许新增，不允许修改已发布文件。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS ops_schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
)
"""


def apply_migrations(conn: sqlite3.Connection) -> int:
    """应用未执行的迁移，返回当前 schema 版本。"""
    conn.execute(_SCHEMA_TABLE)
    applied = {int(row[0]) for row in conn.execute("SELECT version FROM ops_schema_version")}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(path.name.split("_", 1)[0])
        if version not in applied:
            _apply_one(conn, path, version)
            applied.add(version)
    return max(applied, default=0)


def _apply_one(conn: sqlite3.Connection, path: Path, version: int) -> None:
    script = path.read_text(encoding="utf-8")
    try:
        conn.executescript(
            f"BEGIN IMMEDIATE;\n{script}\n"
            f"INSERT INTO ops_schema_version (version, applied_at) "
            f"VALUES ({version}, datetime('now'));\nCOMMIT;"
        )
    except sqlite3.Error:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
