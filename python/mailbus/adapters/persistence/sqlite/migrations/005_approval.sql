-- 005 审批上下文：HITL 三档审批项。
-- 阻塞档请求时同事务把任务置为 blocked；超时由派发器轮询置为 expired。

CREATE TABLE IF NOT EXISTS approval_items (
    approval_id     TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES task_tasks (task_id) ON DELETE CASCADE,
    node_id         TEXT,
    title           TEXT NOT NULL,
    tier            TEXT NOT NULL,
    status          TEXT NOT NULL,
    requester_id    TEXT,
    note            TEXT,
    created_at      REAL NOT NULL,
    expires_at      REAL NOT NULL,
    resolved_by     TEXT,
    resolved_at     REAL,
    resolution_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_approval_items_task
    ON approval_items (task_id, status);

CREATE INDEX IF NOT EXISTS idx_approval_items_due
    ON approval_items (status, expires_at);
