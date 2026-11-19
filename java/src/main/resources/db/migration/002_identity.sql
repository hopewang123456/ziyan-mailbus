-- 002 身份与权限：员工、能力授予、邀请、会话、团队与引导进度。

CREATE TABLE IF NOT EXISTS identity_teams (
    team_id    TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS identity_employees (
    employee_id       TEXT PRIMARY KEY,
    display_name      TEXT NOT NULL,
    account_type      TEXT NOT NULL,
    status            TEXT NOT NULL,
    team_id           TEXT REFERENCES identity_teams (team_id),
    position_id       TEXT,
    seat_id           TEXT,
    data_scope        TEXT NOT NULL DEFAULT 'self',
    file_scope        TEXT NOT NULL DEFAULT '[]',
    endpoint          TEXT,
    endpoint_approved INTEGER NOT NULL DEFAULT 0,
    approved_at       REAL,
    last_heartbeat    REAL,
    created_at        REAL NOT NULL,
    updated_at        REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_identity_employees_status
    ON identity_employees (status, created_at);

CREATE TABLE IF NOT EXISTS identity_capability_grants (
    employee_id TEXT NOT NULL REFERENCES identity_employees (employee_id) ON DELETE CASCADE,
    capability  TEXT NOT NULL,
    granted_at  REAL NOT NULL,
    PRIMARY KEY (employee_id, capability)
);

CREATE TABLE IF NOT EXISTS identity_invites (
    invite_code  TEXT PRIMARY KEY,
    account_type TEXT NOT NULL,
    team_id      TEXT,
    position_id  TEXT,
    data_scope   TEXT NOT NULL DEFAULT 'self',
    capabilities TEXT NOT NULL DEFAULT '[]',
    created_by   TEXT,
    created_at   REAL NOT NULL,
    expires_at   REAL,
    consumed_by  TEXT,
    consumed_at  REAL
);

CREATE TABLE IF NOT EXISTS identity_sessions (
    token_hash  TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL REFERENCES identity_employees (employee_id) ON DELETE CASCADE,
    issued_at   REAL NOT NULL,
    expires_at  REAL,
    revoked_at  REAL
);

CREATE INDEX IF NOT EXISTS idx_identity_sessions_employee
    ON identity_sessions (employee_id);

CREATE TABLE IF NOT EXISTS identity_bootstrap_steps (
    step         TEXT PRIMARY KEY,
    detail       TEXT NOT NULL DEFAULT '{}',
    completed_at REAL NOT NULL
);
