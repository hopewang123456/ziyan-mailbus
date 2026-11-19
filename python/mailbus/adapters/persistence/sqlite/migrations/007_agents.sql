-- 007 Agent 台账：登记 Agent 运行实体，员工通过 agent_id 绑定。

CREATE TABLE IF NOT EXISTS agents (
    agent_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    framework  TEXT NOT NULL DEFAULT '',
    model      TEXT,
    endpoint   TEXT,
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agents_enabled ON agents (enabled, name);

-- 员工绑定 Agent；可空表示暂未绑定（如真人）。
ALTER TABLE identity_employees ADD COLUMN agent_id TEXT;
