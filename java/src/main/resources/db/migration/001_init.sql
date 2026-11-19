-- 001 初始 schema：运行支撑表（业务表随各批次加入）。

CREATE TABLE IF NOT EXISTS ops_outbox (
    event_id      TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    payload       TEXT NOT NULL DEFAULT '{}',
    attempts      INTEGER NOT NULL DEFAULT 0,
    due_at        REAL NOT NULL,
    created_at    REAL NOT NULL,
    dispatched_at REAL,
    last_error    TEXT
);

CREATE INDEX IF NOT EXISTS idx_ops_outbox_due
    ON ops_outbox (due_at) WHERE dispatched_at IS NULL;

CREATE TABLE IF NOT EXISTS ops_timers (
    timer_id   TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    ref_id     TEXT NOT NULL,
    due_at     REAL NOT NULL,
    fired_at   REAL
);

CREATE INDEX IF NOT EXISTS idx_ops_timers_due
    ON ops_timers (due_at) WHERE fired_at IS NULL;

CREATE TABLE IF NOT EXISTS ops_idempotency_keys (
    scope        TEXT NOT NULL,
    key          TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    response     TEXT NOT NULL,
    created_at   REAL NOT NULL,
    PRIMARY KEY (scope, key)
);

CREATE TABLE IF NOT EXISTS ops_audit_log (
    audit_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id  TEXT,
    action    TEXT NOT NULL,
    resource  TEXT,
    detail    TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
