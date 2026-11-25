-- 032 Agent 邀请码自助注册：一次性邀请码，明文不落库。
CREATE TABLE IF NOT EXISTS agent_registration_invites (
    invite_id        TEXT PRIMARY KEY,
    code_hash        TEXT NOT NULL UNIQUE,
    employee_name    TEXT,
    position_id      TEXT,
    capabilities     TEXT NOT NULL DEFAULT '[]',
    permissions      TEXT NOT NULL DEFAULT '["message_read","message_send","result_submit"]',
    agent_type       TEXT NOT NULL DEFAULT 'external',
    channel_type     TEXT NOT NULL DEFAULT 'a2a',
    expires_at       REAL,
    created_by       TEXT NOT NULL,
    created_at       REAL NOT NULL,
    used_by_agent_id TEXT,
    used_at          REAL,
    revoked_at       REAL,
    revoked_by       TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_invites_expires
    ON agent_registration_invites (expires_at);
