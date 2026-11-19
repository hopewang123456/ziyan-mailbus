-- 003 组织上下文：团队归位 org_，新增岗位与工位覆盖层。

-- SQLite 3.25+ 会同步更新 identity_employees.team_id 的外键引用
ALTER TABLE identity_teams RENAME TO org_teams;

CREATE TABLE IF NOT EXISTS org_positions (
    position_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    capabilities TEXT NOT NULL DEFAULT '[]',
    created_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS org_seats (
    seat_id     TEXT PRIMARY KEY,
    team_id     TEXT,
    position_id TEXT,
    x           REAL,
    y           REAL,
    rotation    REAL,
    updated_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_org_seats_team
    ON org_seats (team_id);
