-- 027 任务归档字段；保留天数由环境变量 MAILBUS_TASK_ARCHIVE_DAYS 控制（默认 30），不入库。
ALTER TABLE task_tasks ADD COLUMN archived_at REAL;

CREATE INDEX IF NOT EXISTS idx_task_tasks_archived
    ON task_tasks (archived_at);
