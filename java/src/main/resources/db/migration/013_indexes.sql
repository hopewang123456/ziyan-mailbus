-- 013 索引补强：清理与检索热点字段。
-- created_by：任务可见范围过滤 (owner_id = ? OR created_by = ?)。
CREATE INDEX IF NOT EXISTS idx_task_tasks_created_by
    ON task_tasks (created_by);

-- 心跳巡检：status='active' 且 last_heartbeat 早于 cutoff。
CREATE INDEX IF NOT EXISTS idx_identity_employees_heartbeat
    ON identity_employees (status, last_heartbeat);

-- 操作日志按 created_at 倒序取最近 N 条，避免全表排序。
CREATE INDEX IF NOT EXISTS idx_ops_outbox_created
    ON ops_outbox (created_at);

-- 保留期清理按 created_at 截断。
CREATE INDEX IF NOT EXISTS idx_ops_idempotency_created
    ON ops_idempotency_keys (created_at);

-- 会话清理：已过期或已撤销的旧会话。
CREATE INDEX IF NOT EXISTS idx_identity_sessions_expiry
    ON identity_sessions (expires_at);
