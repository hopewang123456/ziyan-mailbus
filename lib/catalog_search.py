"""mailbus 资源目录检索 — 外部工具、agent 配对等（SQLite FTS5）。

与 lib/search.py 共用 search.db，独立表 catalog。
scan 时自动重建索引；mailbus search --scope catalog|all 可检索。
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Optional

from lib.adapters.integrations.external_tools import (
    external_tools_dir,
    list_adapters_for_agent,
    load_grants,
    load_registry,
    mailbus_root,
)
from .search import _get_conn
from .utils import json_read, _now_iso


def _index_catalog_entry(conn: sqlite3.Connection, entry: dict) -> None:
    doc_id = entry.get("doc_id", "")
    if not doc_id:
        return
    kind = entry.get("kind", "")
    title = entry.get("title", "")
    body = entry.get("body", "")
    agent_id = entry.get("agent_id", "")
    tool_id = entry.get("tool_id", "")
    provider = entry.get("provider", "")
    path = entry.get("path", "")

    conn.execute("DELETE FROM catalog WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM catalog_meta WHERE doc_id = ?", (doc_id,))
    conn.execute(
        """INSERT INTO catalog (doc_id, kind, title, body, agent_id, tool_id, provider, path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (doc_id, kind, title, body, agent_id, tool_id, provider, path),
    )
    conn.execute(
        "INSERT INTO catalog_meta (doc_id, updated_at) VALUES (?, ?)",
        (doc_id, _now_iso()),
    )


def _ensure_catalog_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS catalog USING fts5(
            doc_id UNINDEXED,
            kind,
            title,
            body,
            agent_id,
            tool_id,
            provider,
            path UNINDEXED,
            tokenize='unicode61'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS catalog_meta (
            doc_id TEXT PRIMARY KEY,
            updated_at TEXT
        )
    """)


def _collect_external_tool_entries(data_dir: str) -> list[dict]:
    entries: list[dict] = []
    base = external_tools_dir(data_dir)
    if not os.path.isdir(base):
        return entries

    registry = load_registry(data_dir)
    grants = load_grants(data_dir).get("agent_grants") or {}
    tools_by_id = {t["id"]: t for t in (registry.get("tools") or []) if t.get("id")}

    # 目录索引条目
    entries.append({
        "doc_id": "external-tools:readme",
        "kind": "external_tools_root",
        "title": "mailbus external-tools 外部工具目录",
        "body": "Coze Dify webhook n8n 工作流 agent 配对 adapters registry grants",
        "path": os.path.join(base, "README.md"),
    })

    for tool_id, tool in tools_by_id.items():
        provider = tool.get("provider", "")
        desc = tool.get("description", "")
        granted = [a for a, ids in grants.items() if tool_id in (ids or [])]
        entries.append({
            "doc_id": f"tool:{tool_id}",
            "kind": "external_tool",
            "title": f"外部工具 {tool_id}",
            "body": f"{desc} provider={provider} kind={tool.get('kind','')} agents={','.join(granted)}",
            "tool_id": tool_id,
            "provider": provider,
            "agent_id": ",".join(granted),
            "path": os.path.join(base, "registry.example.json"),
        })

    for agent_id, tool_ids in grants.items():
        for tool_id in tool_ids or []:
            adapter_path = os.path.join(base, "adapters", agent_id, f"{tool_id}.json")
            adapter = json_read(adapter_path, {}) if os.path.isfile(adapter_path) else {}
            tool = tools_by_id.get(tool_id, {})
            entries.append({
                "doc_id": f"adapter:{agent_id}:{tool_id}",
                "kind": "external_tool_adapter",
                "title": f"{agent_id} × {tool_id}",
                "body": " ".join(filter(None, [
                    adapter.get("description", ""),
                    tool.get("description", ""),
                    adapter.get("notes", ""),
                    f"post_invoke={adapter.get('post_invoke','')}",
                ])),
                "agent_id": agent_id,
                "tool_id": tool_id,
                "provider": tool.get("provider", ""),
                "path": adapter_path,
            })

    return entries


def _collect_agent_entries(data_dir: str, agents: dict) -> list[dict]:
    entries = []
    for agent_id, cfg in (agents or {}).items():
        name = cfg.get("name", agent_id)
        role = cfg.get("role", "")
        atype = cfg.get("type", "")
        entries.append({
            "doc_id": f"agent:{agent_id}",
            "kind": "agent",
            "title": f"{name} ({agent_id})",
            "body": f"{role} type={atype} hermes openclaw cline opencode",
            "agent_id": agent_id,
            "path": f"/mailbus/store/inbox/{agent_id}/inbox.json",
        })
    return entries


def _collect_roster_entries(data_dir: str) -> list[dict]:
    path = os.path.join(data_dir, "rules", "organization-roster.json")
    data = json_read(path, {})
    entries = []
    if data.get("team_name"):
        entries.append({
            "doc_id": "org:roster",
            "kind": "organization",
            "title": data.get("team_name", "团队编制"),
            "body": f"headcount={data.get('headcount')} organization 组织架构 编制",
            "path": path,
        })
    for m in data.get("members") or []:
        aid = m.get("id", "")
        entries.append({
            "doc_id": f"org:member:{aid}",
            "kind": "organization_member",
            "title": f"{m.get('icon','')} {m.get('name')} ({aid})",
            "body": " ".join(filter(None, [
                m.get("role_title", ""),
                m.get("role_key", ""),
                m.get("domain", ""),
                m.get("framework", ""),
                f"gender={m.get('gender','')}",
                f"port={m.get('port')}" if m.get("port") else "",
            ])),
            "agent_id": aid,
            "path": path,
        })
    for key, flow in (data.get("flows") or {}).items():
        entries.append({
            "doc_id": f"org:flow:{key}",
            "kind": "organization_flow",
            "title": f"流程 {key}",
            "body": flow,
            "path": path,
        })
    return entries


def index_catalog(data_dir: str, agents: Optional[dict] = None) -> int:
    """重建 catalog FTS 索引。返回索引条数。"""
    if agents is None:
        config_path = os.path.join(data_dir, "config.json")
        agents = json_read(config_path, {}).get("agents") or {}

    conn = _get_conn(data_dir)
    _ensure_catalog_schema(conn)
    try:
        conn.execute("DELETE FROM catalog")
        conn.execute("DELETE FROM catalog_meta")
        count = 0
        for entry in _collect_external_tool_entries(data_dir):
            _index_catalog_entry(conn, entry)
            count += 1
        for entry in _collect_agent_entries(data_dir, agents):
            _index_catalog_entry(conn, entry)
            count += 1
        for entry in _collect_roster_entries(data_dir):
            _index_catalog_entry(conn, entry)
            count += 1
        conn.commit()
        return count
    except sqlite3.Error:
        conn.rollback()
        return 0
    finally:
        conn.close()


def search_catalog(
    data_dir: str,
    query_str: str = "",
    *,
    kind: str = "",
    agent_id: str = "",
    tool_id: str = "",
    limit: int = 20,
) -> list[dict]:
    conn = _get_conn(data_dir)
    _ensure_catalog_schema(conn)
    conditions = []
    params: list[Any] = []

    if query_str:
        conditions.append("catalog MATCH ?")
        params.append(query_str)

    if kind:
        conditions.append("kind = ?")
        params.append(kind)

    if agent_id:
        conditions.append("(agent_id = ? OR agent_id LIKE ?)")
        params.extend([agent_id, f"%{agent_id}%"])

    if tool_id:
        conditions.append("tool_id = ?")
        params.append(tool_id)

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"""
        SELECT catalog.doc_id, catalog.kind, catalog.title, catalog.body,
               catalog.agent_id, catalog.tool_id, catalog.provider, catalog.path,
               meta.updated_at
        FROM catalog
        LEFT JOIN catalog_meta meta ON catalog.doc_id = meta.doc_id
        WHERE {where}
        ORDER BY meta.updated_at DESC
        LIMIT ?
    """
    params.append(limit)

    results = []
    try:
        rows = conn.execute(sql, params).fetchall()
        for row in rows:
            results.append({
                "doc_id": row["doc_id"],
                "kind": row["kind"],
                "title": row["title"],
                "body": (row["body"] or "")[:300],
                "agent_id": row["agent_id"],
                "tool_id": row["tool_id"],
                "provider": row["provider"],
                "path": row["path"],
                "updated_at": row["updated_at"],
            })
    except sqlite3.Error as e:
        print(f"[catalog_search] SQLite 错误: {e}")
    finally:
        conn.close()
    return results


def search_all(
    data_dir: str,
    query_str: str = "",
    *,
    limit: int = 20,
    agents: Optional[dict] = None,
) -> dict:
    from .search import search as search_messages

    return {
        "query": query_str,
        "messages": search_messages(data_dir, query_str=query_str, limit=limit),
        "catalog": search_catalog(data_dir, query_str=query_str, limit=limit),
    }


def list_external_tools_summary(data_dir: str) -> dict:
    """GET /api/external-tools 摘要。"""
    registry = load_registry(data_dir)
    grants = load_grants(data_dir).get("agent_grants") or {}
    base = external_tools_dir(data_dir)
    tools = []
    for t in registry.get("tools") or []:
        tid = t.get("id", "")
        granted = [a for a, ids in grants.items() if tid in (ids or [])]
        adapters = []
        for aid in granted:
            ap = os.path.join(base, "adapters", aid, f"{tid}.json")
            if os.path.isfile(ap):
                ad = json_read(ap, {})
                adapters.append({
                    "agent_id": aid,
                    "enabled": ad.get("enabled", True),
                    "path": ap.replace(mailbus_root(data_dir), "/mailbus").replace("\\", "/"),
                })
        tools.append({
            "id": tid,
            "provider": t.get("provider"),
            "kind": t.get("kind"),
            "description": t.get("description"),
            "agents": granted,
            "adapters": adapters,
        })
    return {
        "external_tools_dir": base.replace(mailbus_root(data_dir), "/mailbus").replace("\\", "/"),
        "tools": tools,
        "agent_grants": grants,
    }
