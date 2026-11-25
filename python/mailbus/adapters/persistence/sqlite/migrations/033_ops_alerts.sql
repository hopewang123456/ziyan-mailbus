-- 033 告警与通知规则：APScheduler 周期评估，firing 期间去重。
CREATE TABLE IF NOT EXISTS ops_alert_rules (
    rule_id         TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    alert_type      TEXT NOT NULL,
    threshold       REAL,
    channel         TEXT NOT NULL,
    target          TEXT,
    silence_seconds INTEGER NOT NULL DEFAULT 300,
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_by      TEXT,
    created_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_alerts (
    alert_id       TEXT PRIMARY KEY,
    rule_id        TEXT,
    type           TEXT NOT NULL,
    severity       TEXT NOT NULL,
    resource_type  TEXT,
    resource_id    TEXT,
    status         TEXT NOT NULL,
    value          TEXT,
    threshold      TEXT,
    first_seen_at  REAL NOT NULL,
    last_seen_at   REAL NOT NULL,
    acked_by       TEXT,
    acked_at       REAL,
    resolved_at    REAL
);

CREATE INDEX IF NOT EXISTS idx_ops_alerts_status
    ON ops_alerts (status, last_seen_at);

CREATE INDEX IF NOT EXISTS idx_ops_alert_rules_type
    ON ops_alert_rules (alert_type, enabled);
