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


def _employee_from_row(
    row: sqlite3.Row,
    capabilities: frozenset[Capability],
    skills: frozenset[str] = frozenset(),
) -> Employee:
    return Employee(
        employee_id=row["employee_id"],
        display_name=row["display_name"],
        account_type=AccountType(row["account_type"]),
        status=EmployeeStatus(row["status"]),
        team_id=row["team_id"],
        position_id=row["position_id"],
        seat_id=row["seat_id"],
        capabilities=capabilities,
        skills=skills,
        data_scope=DataScope(row["data_scope"]),
        file_scope=FileScope(tuple(json.loads(row["file_scope"]))),
        endpoint=row["endpoint"],
        endpoint_approved=bool(row["endpoint_approved"]),
        approved_at=_from_epoch(row["approved_at"]),
        last_heartbeat=_from_epoch(row["last_heartbeat"]),
        agent_id=row["agent_id"],
        deleted_at=_from_epoch(row["deleted_at"]),
        deleted_by=row["deleted_by"],
    )


class SqliteEmployeeRepository:
    def __init__(self, conn: sqlite3.Connection, clock) -> None:
        self._conn = conn
        self._clock = clock

    def get(self, employee_id: str) -> Employee | None:
        row = self._conn.execute(
            "SELECT * FROM identity_employees WHERE employee_id = ? AND deleted_at IS NULL",
            (employee_id,),
        ).fetchone()
        if row is None:
            return None
        caps = {
            Capability(value)
            for (value,) in self._conn.execute(
                "SELECT permission FROM identity_permission_grants WHERE employee_id = ?",
                (employee_id,),
            )
        }
        skills = {
            value
            for (value,) in self._conn.execute(
                "SELECT capability FROM employee_capabilities WHERE employee_id = ?",
                (employee_id,),
            )
        }
        return _employee_from_row(row, frozenset(caps), frozenset(skills))

    def save(self, employee: Employee) -> None:
        now = self._clock.now()
        self._conn.execute(
            "INSERT INTO identity_employees (employee_id, display_name, account_type, status,"
            " team_id, position_id, seat_id, data_scope, file_scope, endpoint, endpoint_approved,"
            " approved_at, last_heartbeat, agent_id, deleted_at, deleted_by, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
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
            " deleted_at = excluded.deleted_at,"
            " deleted_by = excluded.deleted_by,"
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
                _to_epoch(employee.deleted_at) if employee.deleted_at else None,
                employee.deleted_by,
                _to_epoch(now),
                _to_epoch(now),
            ),
        )
        self._save_grants(employee, now)

    def _save_grants(self, employee: Employee, now: datetime) -> None:
        self._conn.execute(
            "DELETE FROM identity_permission_grants WHERE employee_id = ?",
            (employee.employee_id,),
        )
        self._conn.executemany(
            "INSERT INTO identity_permission_grants (employee_id, permission, granted_at)"
            " VALUES (?, ?, ?)",
            [(employee.employee_id, cap.value, _to_epoch(now)) for cap in employee.capabilities],
        )
        self._conn.execute(
            "DELETE FROM employee_capabilities WHERE employee_id = ?",
            (employee.employee_id,),
        )
        self._conn.executemany(
            "INSERT INTO employee_capabilities (employee_id, capability, source, granted_at)"
            " VALUES (?, ?, 'manual', ?)",
            [(employee.employee_id, skill, _to_epoch(now)) for skill in employee.skills],
        )

    def list_by_status(self, status: EmployeeStatus) -> list[Employee]:
        rows = self._conn.execute(
            "SELECT * FROM identity_employees WHERE status = ? AND deleted_at IS NULL"
            " ORDER BY created_at",
            (status.value,),
        ).fetchall()
        return self._build_many(rows)

    def list_all(self) -> list[Employee]:
        rows = self._conn.execute(
            "SELECT * FROM identity_employees WHERE deleted_at IS NULL ORDER BY created_at"
        ).fetchall()
        return self._build_many(rows)

    def active_run_count(self, employee_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM task_node_runs"
            " WHERE assigned_employee_id = ? AND state NOT IN ('done', 'failed', 'skipped')",
            (employee_id,),
        ).fetchone()
        return int(row["n"]) if row is not None else 0

    def soft_delete(self, employee_id: str, actor_id: str, at: datetime) -> None:
        # 与旧注销语义一致：标记 deregistered 并释放工位，
        # 团队/岗位引用由删除团队/岗位前统一清理。
        self._conn.execute(
            "UPDATE identity_employees SET status = 'deregistered', seat_id = NULL,"
            " deleted_at = ?, deleted_by = ?, updated_at = ?"
            " WHERE employee_id = ? AND deleted_at IS NULL",
            (_to_epoch(at), actor_id, _to_epoch(at), employee_id),
        )
        self._conn.execute(
            "DELETE FROM employee_role_bindings WHERE employee_id = ?", (employee_id,)
        )
        self._conn.execute(
            "DELETE FROM employee_capabilities WHERE employee_id = ?", (employee_id,)
        )

    def clear_team_reference(self, team_id: str) -> None:
        """团队删除前解除已注销员工的归属，避免遗留悬空引用。"""
        self._clear_reference("team_id", team_id)

    def clear_position_reference(self, position_id: str) -> None:
        """岗位删除前解除已注销员工的归属，避免遗留悬空引用。"""
        self._clear_reference("position_id", position_id)

    def _clear_reference(self, column: str, unit_id: str) -> None:
        # column 仅由上面两个方法传入固定列名，不接受外部输入。
        self._conn.execute(
            f"UPDATE identity_employees SET {column} = NULL, updated_at = ?"
            f" WHERE {column} = ? AND status = 'deregistered'",
            (_to_epoch(self._clock.now()), unit_id),
        )

    def list_stale_active(self, cutoff: datetime) -> list[Employee]:
        """心跳巡检候选：active、有过心跳且早于 cutoff 的员工（走覆盖索引）。

        两类账号不参与巡检：last_heartbeat IS NULL 的（从未报告在勤，如外部导入数据），
        以及持全量权限的运维入口（超管无在勤义务），避免被误标离线污染总览与审计。
        """
        rows = self._conn.execute(
            "SELECT * FROM identity_employees"
            " WHERE status = ? AND last_heartbeat IS NOT NULL AND last_heartbeat < ?"
            " AND deleted_at IS NULL"
            " AND employee_id NOT IN ("
            "SELECT employee_id FROM identity_permission_grants WHERE permission = ?)"
            " ORDER BY created_at",
            (EmployeeStatus.ACTIVE.value, _to_epoch(cutoff), Capability.ALL.value),
        ).fetchall()
        return self._build_many(rows)

    def _build_many(self, rows: list[sqlite3.Row]) -> list[Employee]:
        """批量装配：员工行一次取回，权限与业务技能各一次取回，避免 N+1。"""
        if not rows:
            return []
        grants: dict[str, set[Capability]] = {}
        for employee_id, value in self._conn.execute(
            "SELECT employee_id, permission FROM identity_permission_grants"
        ):
            grants.setdefault(employee_id, set()).add(Capability(value))
        skills: dict[str, set[str]] = {}
        for employee_id, value in self._conn.execute(
            "SELECT employee_id, capability FROM employee_capabilities"
        ):
            skills.setdefault(employee_id, set()).add(value)
        return [
            _employee_from_row(
                row,
                frozenset(grants.get(row["employee_id"], ())),
                frozenset(skills.get(row["employee_id"], ())),
            )
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
            " data_scope, permissions, created_by, created_at, expires_at,"
            " revoked_at, revoked_by)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                invite.invite_code,
                invite.account_type.value,
                invite.team_id,
                invite.position_id,
                invite.data_scope.value,
                json.dumps([cap.value for cap in invite.permissions], ensure_ascii=False),
                invite.created_by,
                now,
                _to_epoch(invite.expires_at) if invite.expires_at else None,
                _to_epoch(invite.revoked_at) if invite.revoked_at else None,
                invite.revoked_by,
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
            permissions=frozenset(Capability(v) for v in json.loads(row["permissions"])),
            created_by=row["created_by"],
            created_at=_from_epoch(row["created_at"]),
            expires_at=_from_epoch(row["expires_at"]),
            consumed_by=row["consumed_by"],
            consumed_at=_from_epoch(row["consumed_at"]),
            revoked_at=_from_epoch(row["revoked_at"]),
            revoked_by=row["revoked_by"],
        )

    def consume(self, invite_code: str, employee_id: str, at: datetime) -> bool:
        cursor = self._conn.execute(
            "UPDATE identity_invites SET consumed_by = ?, consumed_at = ?"
            " WHERE invite_code = ? AND consumed_at IS NULL AND revoked_at IS NULL",
            (employee_id, _to_epoch(at), invite_code),
        )
        return cursor.rowcount > 0

    def revoke(self, invite_code: str, actor_id: str, at: datetime) -> bool:
        cursor = self._conn.execute(
            "UPDATE identity_invites SET revoked_at = ?, revoked_by = ?"
            " WHERE invite_code = ? AND consumed_at IS NULL AND revoked_at IS NULL",
            (_to_epoch(at), actor_id, invite_code),
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
