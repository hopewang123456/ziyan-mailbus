-- 024 超时升级记录 + 团队负责人（level 列由 028 追加）。
CREATE TABLE IF NOT EXISTS task_escalations (
    escalation_id TEXT PRIMARY KEY,
    task_id       TEXT NOT NULL,
    run_id        TEXT,
    approval_id   TEXT,
    reason        TEXT NOT NULL,
    escalated_to  TEXT NOT NULL,
    escalated_at  REAL NOT NULL,
    resolved_by   TEXT,
    resolved_at   REAL,
    resolution    TEXT
);

CREATE INDEX IF NOT EXISTS idx_escalations_task
    ON task_escalations (task_id, resolved_at);

ALTER TABLE org_teams ADD COLUMN leader_employee_id TEXT;
