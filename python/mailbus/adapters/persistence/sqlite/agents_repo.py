"""Agent 台账与注册邀请码的 SQLite 仓储。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from mailbus.core.agents.models import Agent, AgentInvite


def _to_epoch(value: datetime) -> float:
    return value.timestamp()


def _from_epoch(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


def _text_set(value: str | None) -> frozenset[str]:
    if not value:
        return frozenset()
    try:
        parsed = json.loads(value)
    except ValueError:
        return frozenset()
    return frozenset(str(item) for item in parsed) if isinstance(parsed, list) else frozenset()


def _agent_from_row(row: sqlite3.Row) -> Agent:
    return Agent(
        agent_id=row["agent_id"],
        name=row["name"],
        framework=row["framework"],
        model=row["model"],
        endpoint=row["endpoint"],
        enabled=bool(row["enabled"]),
        created_at=_from_epoch(row["created_at"]),
        updated_at=_from_epoch(row["updated_at"]),
        agent_type=row["agent_type"] or "service",
        channel_type=row["channel_type"] or "a2a",
        endpoint_token=row["endpoint_token"],
        endpoint_token_lookup_hash=row["endpoint_token_lookup_hash"],
        endpoint_token_prev=row["endpoint_token_prev"],
        endpoint_token_prev_lookup_hash=row["endpoint_token_prev_lookup_hash"],
        endpoint_token_prev_expires_at=_from_epoch(row["endpoint_token_prev_expires_at"]),
        last_seen_at=_from_epoch(row["last_seen_at"]),
        pending_endpoint=row["pending_endpoint"],
        endpoint_review_status=row["endpoint_review_status"] or "pending",
        endpoint_approved_by=row["endpoint_approved_by"],
        endpoint_approved_at=_from_epoch(row["endpoint_approved_at"]),
        deleted_at=_from_epoch(row["deleted_at"]),
        deleted_by=row["deleted_by"],
    )


def _invite_from_row(row: sqlite3.Row) -> AgentInvite:
    return AgentInvite(
        invite_id=row["invite_id"],
        code_hash=row["code_hash"],
        employee_name=row["employee_name"],
        position_id=row["position_id"],
        capabilities=_text_set(row["capabilities"]),
        permissions=_text_set(row["permissions"]),
        data_scope=row["data_scope"] or "self",
        agent_type=row["agent_type"] or "external",
        channel_type=row["channel_type"] or "a2a",
        expires_at=_from_epoch(row["expires_at"]),
        created_by=row["created_by"],
        created_at=_from_epoch(row["created_at"]),
        used_by_agent_id=row["used_by_agent_id"],
        used_at=_from_epoch(row["used_at"]),
        revoked_at=_from_epoch(row["revoked_at"]),
        revoked_by=row["revoked_by"],
    )


class SqliteAgentRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def get(self, agent_id: str) -> Agent | None:
        row = self._conn.execute(
            "SELECT * FROM agents WHERE agent_id = ? AND deleted_at IS NULL", (agent_id,)
        ).fetchone()
        return None if row is None else _agent_from_row(row)

    def save(self, agent: Agent) -> None:
        now = agent.updated_at or self._clock.now()
        self._conn.execute(_AGENT_UPSERT, _agent_params(agent, agent.created_at or now, now))

    def list_all(self) -> list[Agent]:
        rows = self._conn.execute(
            "SELECT * FROM agents WHERE deleted_at IS NULL ORDER BY created_at, agent_id"
        ).fetchall()
        return [_agent_from_row(row) for row in rows]

    def list_page(self, limit: int, offset: int) -> tuple[list[Agent], int]:
        total = self._conn.execute(
            "SELECT COUNT(*) FROM agents WHERE deleted_at IS NULL"
        ).fetchone()[0]
        rows = self._conn.execute(
            "SELECT * FROM agents WHERE deleted_at IS NULL"
            " ORDER BY created_at, agent_id LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_agent_from_row(row) for row in rows], int(total)

    def find_by_token_lookup(self, lookup_hash: str) -> Agent | None:
        row = self._conn.execute(
            "SELECT * FROM agents WHERE deleted_at IS NULL AND ("
            " endpoint_token_lookup_hash = ? OR ("
            " endpoint_token_prev_lookup_hash = ?"
            " AND (endpoint_token_prev_expires_at IS NULL"
            "      OR endpoint_token_prev_expires_at > ?)))",
            (lookup_hash, lookup_hash, self._clock.now().timestamp()),
        ).fetchone()
        return None if row is None else _agent_from_row(row)

    def delete(self, agent_id: str) -> None:
        self._conn.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))

    def soft_delete(self, agent_id: str, actor_id: str, now: datetime) -> None:
        self._conn.execute(
            "UPDATE agents SET deleted_at = ?, deleted_by = ?, endpoint_token = NULL,"
            " endpoint_token_lookup_hash = NULL, endpoint_token_prev = NULL,"
            " endpoint_token_prev_lookup_hash = NULL,"
            " endpoint_token_prev_expires_at = NULL, updated_at = ?"
            " WHERE agent_id = ? AND deleted_at IS NULL",
            (_to_epoch(now), actor_id, _to_epoch(now), agent_id),
        )

    # ---- 注册邀请码 ----

    def add_invite(self, invite: AgentInvite) -> None:
        self.save_invite(invite)

    def get_invite(self, invite_id: str) -> AgentInvite | None:
        row = self._conn.execute(
            "SELECT * FROM agent_registration_invites WHERE invite_id = ?", (invite_id,)
        ).fetchone()
        return None if row is None else _invite_from_row(row)

    def get_invite_by_hash(self, code_hash: str) -> AgentInvite | None:
        row = self._conn.execute(
            "SELECT * FROM agent_registration_invites WHERE code_hash = ?", (code_hash,)
        ).fetchone()
        return None if row is None else _invite_from_row(row)

    def list_invites(self, limit: int, offset: int) -> tuple[list[AgentInvite], int]:
        total = self._conn.execute(
            "SELECT COUNT(*) FROM agent_registration_invites"
        ).fetchone()[0]
        rows = self._conn.execute(
            "SELECT * FROM agent_registration_invites"
            " ORDER BY created_at DESC, invite_id LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [_invite_from_row(row) for row in rows], int(total)

    def save_invite(self, invite: AgentInvite) -> None:
        self._conn.execute(
            "INSERT INTO agent_registration_invites (invite_id, code_hash, employee_name,"
            " position_id, capabilities, permissions, data_scope, agent_type, channel_type,"
            " expires_at, created_by, created_at, used_by_agent_id, used_at, revoked_at,"
            " revoked_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (invite_id) DO UPDATE SET"
            " used_by_agent_id = excluded.used_by_agent_id,"
            " used_at = excluded.used_at,"
            " revoked_at = excluded.revoked_at, revoked_by = excluded.revoked_by",
            (
                invite.invite_id,
                invite.code_hash,
                invite.employee_name,
                invite.position_id,
                json.dumps(sorted(invite.capabilities), ensure_ascii=False),
                json.dumps(sorted(invite.permissions), ensure_ascii=False),
                invite.data_scope,
                invite.agent_type,
                invite.channel_type,
                _nullable_epoch(invite.expires_at),
                invite.created_by,
                _nullable_epoch(invite.created_at) or self._clock.now().timestamp(),
                invite.used_by_agent_id,
                _nullable_epoch(invite.used_at),
                _nullable_epoch(invite.revoked_at),
                invite.revoked_by,
            ),
        )


def _nullable_epoch(value: datetime | None) -> float | None:
    return None if value is None else _to_epoch(value)


_AGENT_UPSERT = (
    "INSERT INTO agents (agent_id, name, framework, model, endpoint, enabled,"
    " agent_type, channel_type, endpoint_token, endpoint_token_lookup_hash,"
    " endpoint_token_prev, endpoint_token_prev_lookup_hash,"
    " endpoint_token_prev_expires_at, last_seen_at, pending_endpoint,"
    " endpoint_review_status, endpoint_approved_by, endpoint_approved_at,"
    " deleted_at, deleted_by, created_at, updated_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    " ON CONFLICT (agent_id) DO UPDATE SET"
    " name = excluded.name, framework = excluded.framework,"
    " model = excluded.model, endpoint = excluded.endpoint,"
    " enabled = excluded.enabled, agent_type = excluded.agent_type,"
    " channel_type = excluded.channel_type,"
    " endpoint_token = excluded.endpoint_token,"
    " endpoint_token_lookup_hash = excluded.endpoint_token_lookup_hash,"
    " endpoint_token_prev = excluded.endpoint_token_prev,"
    " endpoint_token_prev_lookup_hash = excluded.endpoint_token_prev_lookup_hash,"
    " endpoint_token_prev_expires_at = excluded.endpoint_token_prev_expires_at,"
    " last_seen_at = excluded.last_seen_at,"
    " pending_endpoint = excluded.pending_endpoint,"
    " endpoint_review_status = excluded.endpoint_review_status,"
    " endpoint_approved_by = excluded.endpoint_approved_by,"
    " endpoint_approved_at = excluded.endpoint_approved_at,"
    " deleted_at = excluded.deleted_at, deleted_by = excluded.deleted_by,"
    " updated_at = excluded.updated_at"
)


def _agent_params(agent: Agent, created: datetime, now: datetime) -> tuple[object, ...]:
    return (
        agent.agent_id, agent.name, agent.framework, agent.model, agent.endpoint,
        int(agent.enabled), agent.agent_type, agent.channel_type,
        agent.endpoint_token, agent.endpoint_token_lookup_hash,
        agent.endpoint_token_prev, agent.endpoint_token_prev_lookup_hash,
        _nullable_epoch(agent.endpoint_token_prev_expires_at),
        _nullable_epoch(agent.last_seen_at), agent.pending_endpoint,
        agent.endpoint_review_status, agent.endpoint_approved_by,
        _nullable_epoch(agent.endpoint_approved_at), _nullable_epoch(agent.deleted_at),
        agent.deleted_by, _to_epoch(created), _to_epoch(now),
    )
