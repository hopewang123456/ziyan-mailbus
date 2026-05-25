"""ziyan-mailbus 消息检索（SQLite FTS5）

将消息索引到 SQLite 全文检索引擎，提供 mailbus search 命令。"""
import os
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path

from .models import MsgStatus
from .utils import resolve_paths, _now_iso


SEARCH_DB = "search.db"


def _get_db_path(data_dir: str) -> str:
    return os.path.join(data_dir, SEARCH_DB)


def _get_conn(data_dir: str):
    """获取 SQLite 连接（自动创建表）"""
    db_path = _get_db_path(data_dir)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS messages USING fts5(
            msg_id, from_agent, to_agent, type, content, status,
            tokenize='unicode61'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            msg_id TEXT PRIMARY KEY,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    return conn


def index_message(data_dir: str, msg: dict):
    """将一条消息加入全文索引"""
    conn = _get_conn(data_dir)
    msg_id = msg.get("id", "")
    content = msg.get("content", "")
    from_ = msg.get("from", "")
    to_ = msg.get("to", "")
    msg_type = msg.get("type", "")
    status = msg.get("status", "")

    # 跳过空消息
    if not msg_id:
        return

    try:
        # 先删除旧索引（幂等）
        conn.execute("DELETE FROM messages WHERE msg_id = ?", (msg_id,))
        conn.execute("DELETE FROM meta WHERE msg_id = ?", (msg_id,))

        # 写入 FTS
        conn.execute(
            "INSERT INTO messages (msg_id, from_agent, to_agent, type, content, status) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, from_, to_, msg_type, content, status),
        )
        conn.execute(
            "INSERT INTO meta (msg_id, created_at, updated_at) VALUES (?, ?, ?)",
            (msg_id, msg.get("created_at", ""), _now_iso()),
        )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
    finally:
        conn.close()


def scan_and_index(data_dir: str, agents: dict):
    """扫描所有 inbox 并索引新消息"""
    paths = resolve_paths(data_dir)
    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        try:
            import json as _json
            with open(inbox_file) as f:
                data = _json.load(f)
            from .models import Inbox
            inbox = Inbox.from_dict(data)
            for msg in inbox.messages:
                if isinstance(msg, dict):
                    index_message(data_dir, msg)
                else:
                    index_message(data_dir, msg.to_dict())
        except (FileNotFoundError, json.JSONDecodeError):
            pass


def search(data_dir: str, query_str: str = "", from_agent: str = "",
           to_agent: str = "", msg_type: str = "", status: str = "",
           limit: int = 20) -> list:
    """
    搜索消息。

    参数:
        query_str: FTS5 全文搜索关键词
        from_agent: 发件人过滤
        to_agent: 收件人过滤
        msg_type: 消息类型过滤
        status: 状态过滤
        limit: 最大返回条数

    返回: [{"msg_id", "from", "to", "type", "content", "status", "created_at"}, ...]
    """
    conn = _get_conn(data_dir)
    conditions = []
    params = []

    if query_str:
        conditions.append("messages MATCH ?")
        # FTS5 查询语法：用双引号精确匹配，空格 OR 模糊匹配
        params.append(query_str)

    if from_agent:
        conditions.append("from_agent = ?")
        params.append(from_agent)

    if to_agent:
        conditions.append("to_agent = ?")
        params.append(to_agent)

    if msg_type:
        conditions.append("type = ?")
        params.append(msg_type)

    if status:
        conditions.append("status = ?")
        params.append(status)

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"""
        SELECT m.msg_id, m.from_agent, m.to_agent, m.type, m.content, m.status,
               meta.created_at
        FROM messages m
        LEFT JOIN meta ON m.msg_id = meta.msg_id
        WHERE {where}
        ORDER BY meta.created_at DESC
        LIMIT ?
    """
    params.append(limit)

    results = []
    try:
        rows = conn.execute(sql, params).fetchall()
        for row in rows:
            results.append({
                "msg_id": row["msg_id"],
                "from": row["from_agent"],
                "to": row["to_agent"],
                "type": row["type"],
                "content": row["content"][:200],  # 只显示前 200 字符
                "status": row["status"],
                "created_at": row["created_at"],
            })
    except sqlite3.Error as e:
        print(f"[search] SQLite 错误: {e}")
    finally:
        conn.close()

    return results
