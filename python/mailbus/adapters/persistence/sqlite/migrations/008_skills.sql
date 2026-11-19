-- 008 技能包：登记来源、探测版本与绑定（Agent 默认 / 员工覆盖）。

CREATE TABLE IF NOT EXISTS skills_packages (
    package_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    source_uri      TEXT NOT NULL,
    entry           TEXT NOT NULL DEFAULT 'SKILL.md',
    version         TEXT NOT NULL DEFAULT '',
    enabled         INTEGER NOT NULL DEFAULT 1,
    note            TEXT NOT NULL DEFAULT '',
    last_checked_at REAL,
    last_error      TEXT,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS skills_bindings (
    package_id  TEXT NOT NULL REFERENCES skills_packages (package_id) ON DELETE CASCADE,
    target_type TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  REAL NOT NULL,
    PRIMARY KEY (package_id, target_type, target_id)
);

CREATE INDEX IF NOT EXISTS idx_skills_bindings_target
    ON skills_bindings (target_type, target_id);
