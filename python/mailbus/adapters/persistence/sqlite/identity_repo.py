"""身份上下文的 SQLite 仓储实现。

只做行 ↔ 聚合的转换；事务边界仍由 UoW 负责。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from mailbus.core.identity.models import Employee, Invite
from mailbus.core.identity.values import AccountType, EmployeeStatus
from mailbus.core.shared.values import Capability, DataScope, FileScope


def _to_epoch(value: datetime) -> float:
    return value.timestamp()


def _from_epoch(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, tz=timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _employee_from_row(row: sqlite3.Row, capabilities: frozenset[Capability]) -> Employee:
    return Employee(
        employee_id=row["employee_id"],
        display_name=row["display_name"],
        account_type=AccountType(row["account_type"]),
        status=EmployeeStatus(row["status"]),
        team_id=row["team_id"],
        position_id=row["position_id"],
        seat_id=row["seat_id"],
        capabilities=capabilities,
        data_scope=DataScope(row["data_scope"]),
        file_scope=FileScope(tuple(json.loads(row["file_scope"]))),
        endpoint=row["endpoint"],
        endpoint_approved=bool(row["endpoint_approved"]),
        approved_at=_from_epoch(row["approved_at"]),
        last_heartbeat=_from_epoch(row["last_heartbeat"]),
        agent_id=row["agent_id"],
    )


class SqliteEmployeeRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def get(self, employee_id: str) -> Employee | None:
        row = self._conn.execute(
            "SELECT * FROM identity_employees WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if row is None:
            return None
        caps = {
            Capability(value)
            for (value,) in self._conn.execute(
                "SELECT capability FROM identity_capability_grants WHERE employee_id = ?",
                (employee_id,),
            )
        }
        return _employee_from_row(row, frozenset(caps))

    def save(self, employee: Employee) -> None:
        now = self._clock.now()
        self._conn.execute(
            "INSERT INTO identity_employees (employee_id, display_name, account_type, status,"
            " team_id, position_id, seat_id, data_scope, file_scope, endpoint, endpoint_approved,"
            " approved_at, last_heartbeat, agent_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (employee_id) DO UPDATE SET"
            " display_name = excluded.display_name,"
            " account_type = excluded.account_type,"
            " status = excluded.status,"
            " team_id = excluded.team_id,"
            " position_id = excluded.position_id,"
            " seat_id = excluded.seat_id,"
            " data_scope = excluded.data_scope,"
            " file_scope = excluded.file_scope,"
            " endpoint = excluded.endpoint,"
            " endpoint_approved = excluded.endpoint_approved,"
            " approved_at = excluded.approved_at,"
            " last_heartbeat = excluded.last_heartbeat,"
            " agent_id = excluded.agent_id,"
            " updated_at = excluded.updated_at",
            (
                employee.employee_id,
                employee.display_name,
                employee.account_type.value,
                employee.status.value,
                employee.team_id,
                employee.position_id,
                employee.seat_id,
                employee.data_scope.value,
                json.dumps(list(employee.file_scope.paths), ensure_ascii=False),
                employee.endpoint,
                int(employee.endpoint_approved),
                _to_epoch(employee.approved_at) if employee.approved_at else None,
                _to_epoch(employee.last_heartbeat) if employee.last_heartbeat else None,
                employee.agent_id,
                _to_epoch(now),
                _to_epoch(now),
            ),
        )
        self._conn.execute(
            "DELETE FROM identity_capability_grants WHERE employee_id = ?", (employee.employee_id,)
        )
        self._conn.executemany(
            "INSERT INTO identity_capability_grants (employee_id, capability, granted_at)"
            " VALUES (?, ?, ?)",
            [(employee.employee_id, cap.value, _to_epoch(now)) for cap in employee.capabilities],
        )

    def list_by_status(self, status: EmployeeStatus) -> list[Employee]:
        rows = self._conn.execute(
            "SELECT * FROM identity_employees WHERE status = ? ORDER BY created_at",
            (status.value,),
        ).fetchall()
        return self._build_many(rows)

    def list_all(self) -> list[Employee]:
        rows = self._conn.execute(
            "SELECT * FROM identity_employees ORDER BY created_at"
        ).fetchall()
        return self._build_many(rows)

    def list_stale_active(self, cutoff: datetime) -> list[Employee]:
        """心跳巡检候选：active、有过心跳且早于 cutoff 的员工（走覆盖索引）。

        两类账号不参与巡检：last_heartbeat IS NULL 的（从未报告在勤，如外部导入数据），
        以及持全量权限的运维入口（超管无在勤义务），避免被误标离线污染总览与审计。
        """
        rows = self._conn.execute(
            "SELECT * FROM identity_employees"
            " WHERE status = ? AND last_heartbeat IS NOT NULL AND last_heartbeat < ?"
            " AND employee_id NOT IN ("
            "SELECT employee_id FROM identity_capability_grants WHERE capability = ?)"
            " ORDER BY created_at",
            (EmployeeStatus.ACTIVE.value, _to_epoch(cutoff), Capability.ALL.value),
        ).fetchall()
        return self._build_many(rows)

    def _build_many(self, rows: list[sqlite3.Row]) -> list[Employee]:
        """批量装配：员工行一次取回，能力授权一次取回，避免逐员工 N+1。"""
        if not rows:
            return []
        grants: dict[str, set[Capability]] = {}
        for employee_id, value in self._conn.execute(
            "SELECT employee_id, capability FROM identity_capability_grants"
        ):
            grants.setdefault(employee_id, set()).add(Capability(value))
        return [
            _employee_from_row(row, frozenset(grants.get(row["employee_id"], ())))
            for row in rows
        ]


class SqliteInviteRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, invite: Invite) -> None:
        now = _to_epoch(invite.created_at or self._clock.now())
        self._conn.execute(
            "INSERT INTO identity_invites (invite_code, account_type, team_id, position_id,"
            " data_scope, capabilities, created_by, created_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                invite.invite_code,
                invite.account_type.value,
                invite.team_id,
                invite.position_id,
                invite.data_scope.value,
                json.dumps([cap.value for cap in invite.capabilities], ensure_ascii=False),
                invite.created_by,
                now,
                _to_epoch(invite.expires_at) if invite.expires_at else None,
            ),
        )

    def get(self, invite_code: str) -> Invite | None:
        row = self._conn.execute(
            "SELECT * FROM identity_invites WHERE invite_code = ?", (invite_code,)
        ).fetchone()
        if row is None:
            return None
        return Invite(
            invite_code=row["invite_code"],
            account_type=AccountType(row["account_type"]),
            team_id=row["team_id"],
            position_id=row["position_id"],
            data_scope=DataScope(row["data_scope"]),
            capabilities=frozenset(Capability(v) for v in json.loads(row["capabilities"])),
            created_by=row["created_by"],
            created_at=_from_epoch(row["created_at"]),
            expires_at=_from_epoch(row["expires_at"]),
            consumed_by=row["consumed_by"],
            consumed_at=_from_epoch(row["consumed_at"]),
        )

    def consume(self, invite_code: str, employee_id: str, at: datetime) -> bool:
        cursor = self._conn.execute(
            "UPDATE identity_invites SET consumed_by = ?, consumed_at = ?"
            " WHERE invite_code = ? AND consumed_at IS NULL",
            (employee_id, _to_epoch(at), invite_code),
        )
        return cursor.rowcount > 0


class SqliteSessionRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def issue(
        self,
        employee_id: str,
        token: str,
        issued_at: datetime,
        expires_at: datetime | None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO identity_sessions (token_hash, employee_id, issued_at, expires_at)"
            " VALUES (?, ?, ?, ?)",
            (
                _hash_token(token),
                employee_id,
                _to_epoch(issued_at),
                _to_epoch(expires_at) if expires_at else None,
            ),
        )

    def resolve(self, token: str, now: datetime) -> str | None:
        row = self._conn.execute(
            "SELECT employee_id FROM identity_sessions"
            " WHERE token_hash = ? AND revoked_at IS NULL"
            " AND (expires_at IS NULL OR expires_at > ?)",
            (_hash_token(token), _to_epoch(now)),
        ).fetchone()
        return None if row is None else row["employee_id"]

    def revoke(self, token: str, at: datetime) -> None:
        self._conn.execute(
            "UPDATE identity_sessions SET revoked_at = ?"
            " WHERE token_hash = ? AND revoked_at IS NULL",
            (_to_epoch(at), _hash_token(token)),
        )

    def revoke_all(self, employee_id: str, at: datetime) -> None:
        self._conn.execute(
            "UPDATE identity_sessions SET revoked_at = ?"
            " WHERE employee_id = ? AND revoked_at IS NULL",
            (_to_epoch(at), employee_id),
        )


class SqliteBootstrapRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def completed(self) -> dict[str, dict]:
        rows = self._conn.execute(
            "SELECT step, detail FROM identity_bootstrap_steps"
        ).fetchall()
        return {row["step"]: json.loads(row["detail"]) for row in rows}

    def mark(self, step: str, detail: dict, at: datetime) -> None:
        self._conn.execute(
            "INSERT INTO identity_bootstrap_steps (step, detail, completed_at) VALUES (?, ?, ?)"
            " ON CONFLICT (step) DO UPDATE SET detail = excluded.detail,"
            " completed_at = excluded.completed_at",
            (step, json.dumps(detail, ensure_ascii=False), _to_epoch(at)),
        )
