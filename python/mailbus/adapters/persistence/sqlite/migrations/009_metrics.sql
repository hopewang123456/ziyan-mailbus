-- 009 指标治理：告警规则与大盘布局（dashboard as config）。

CREATE TABLE IF NOT EXISTS metrics_rules (
    rule_id   TEXT PRIMARY KEY,
    metric    TEXT NOT NULL,
    op        TEXT NOT NULL,
    threshold REAL NOT NULL,
    severity  TEXT NOT NULL,
    enabled   INTEGER NOT NULL DEFAULT 0,
    note      TEXT NOT NULL DEFAULT '',
    actions   TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS metrics_layout (
    id     INTEGER PRIMARY KEY CHECK (id = 1),
    hidden TEXT NOT NULL DEFAULT '[]'
);

INSERT OR IGNORE INTO metrics_rules
    (rule_id, metric, op, threshold, severity, enabled, note, actions)
VALUES
    ('tasks_active_backlog', 'tasks.active', '>', 20, 'warn', 0,
     '活跃任务持续偏高', '[]'),
    ('tasks_failed_today', 'tasks.failed_today', '>', 0, 'critical', 1,
     '当天出现失败任务', '[]'),
    ('agents_offline', 'agents.online', '<', 1, 'warn', 0,
     '无在线 Agent', '[]');

INSERT OR IGNORE INTO metrics_layout (id, hidden) VALUES (1, '[]');
